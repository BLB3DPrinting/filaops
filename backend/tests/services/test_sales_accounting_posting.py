"""Sales accounting posting tests for quote-to-cash flow."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.accounting import GLAccount, GLJournalEntry, GLJournalEntryLine
from app.models.bom import BOM, BOMLine
from app.models.inventory import Inventory, InventoryTransaction
from app.models.material import Color, MaterialInventory, MaterialType
from app.models.payment import Payment
from app.models.sales_order import SalesOrderLine


def _entry_lines(db, *, source_type: str, source_id: int) -> dict[str, dict[str, Decimal]]:
    rows = (
        db.query(
            GLAccount.account_code,
            GLJournalEntryLine.debit_amount,
            GLJournalEntryLine.credit_amount,
        )
        .join(GLJournalEntryLine, GLJournalEntryLine.account_id == GLAccount.id)
        .join(GLJournalEntry, GLJournalEntry.id == GLJournalEntryLine.journal_entry_id)
        .filter(
            GLJournalEntry.source_type == source_type,
            GLJournalEntry.source_id == source_id,
            GLJournalEntry.status == "posted",
        )
        .all()
    )
    return {
        row.account_code: {
            "debit": row.debit_amount or Decimal("0"),
            "credit": row.credit_amount or Decimal("0"),
        }
        for row in rows
    }


def test_mark_sent_posts_invoice_receivable_revenue_tax_and_shipping(
    db, make_product, make_sales_order
):
    from app.services.invoice_service import create_invoice, mark_sent

    product = make_product(selling_price=Decimal("20.00"))
    order = make_sales_order(
        product_id=product.id,
        quantity=1,
        unit_price=Decimal("20.00"),
        status="confirmed",
    )
    order.tax_rate = Decimal("0.0875")
    order.tax_amount = Decimal("1.75")
    order.shipping_cost = Decimal("5.00")
    order.grand_total = Decimal("26.75")
    invoice = create_invoice(db, order.id)

    mark_sent(db, invoice.id)

    lines = _entry_lines(db, source_type="invoice", source_id=invoice.id)
    assert lines["1100"]["debit"] == Decimal("26.75")
    assert lines["4000"]["credit"] == Decimal("20.00")
    assert lines["2100"]["credit"] == Decimal("1.75")
    assert lines["4200"]["credit"] == Decimal("5.00")


def test_record_payment_posts_invoice_if_needed_and_payment_receipt(
    db, make_product, make_sales_order
):
    from app.models.payment import Payment
    from app.services.invoice_service import create_invoice, record_payment

    product = make_product(selling_price=Decimal("45.00"))
    order = make_sales_order(
        product_id=product.id,
        quantity=1,
        unit_price=Decimal("45.00"),
        status="confirmed",
    )
    order.tax_amount = Decimal("3.15")
    order.shipping_cost = Decimal("5.00")
    order.grand_total = Decimal("53.15")
    invoice = create_invoice(db, order.id)

    record_payment(db, invoice.id, Decimal("53.15"), "credit_card", reference="txn-53")

    payment = db.query(Payment).filter(Payment.sales_order_id == order.id).one()
    invoice_lines = _entry_lines(db, source_type="invoice", source_id=invoice.id)
    payment_lines = _entry_lines(db, source_type="payment", source_id=payment.id)

    assert invoice_lines["1100"]["debit"] == Decimal("53.15")
    assert payment_lines["1000"]["debit"] == Decimal("53.15")
    assert payment_lines["1100"]["credit"] == Decimal("53.15")


def test_update_order_payment_status_posts_manual_payment_once(db, make_sales_order):
    from app.services.payment_service import update_order_payment_status

    order = make_sales_order(
        quantity=1,
        unit_price=Decimal("75.00"),
        status="confirmed",
        payment_status="pending",
    )
    payment = Payment(
        payment_number=f"PAY-POST-{order.id}",
        sales_order_id=order.id,
        amount=Decimal("25.00"),
        payment_method="cash",
        payment_type="payment",
        status="completed",
        payment_date=datetime.now(timezone.utc),
    )
    db.add(payment)
    db.flush()

    update_order_payment_status(db, order)
    update_order_payment_status(db, order)

    entries = (
        db.query(GLJournalEntry)
        .filter(
            GLJournalEntry.source_type == "payment",
            GLJournalEntry.source_id == payment.id,
        )
        .all()
    )
    lines = _entry_lines(db, source_type="payment", source_id=payment.id)

    assert len(entries) == 1
    assert lines["1000"]["debit"] == Decimal("25.00")
    assert lines["1100"]["credit"] == Decimal("25.00")


def test_void_payment_posts_cash_ar_reversal(client, db, make_sales_order):
    order = make_sales_order(
        quantity=1,
        unit_price=Decimal("30.00"),
        status="confirmed",
        payment_status="pending",
    )
    response = client.post(
        "/api/v1/payments",
        json={
            "sales_order_id": order.id,
            "amount": "30.00",
            "payment_method": "cash",
        },
    )
    assert response.status_code == 201
    payment_id = response.json()["id"]

    void_response = client.delete(f"/api/v1/payments/{payment_id}")
    assert void_response.status_code == 204

    lines = _entry_lines(db, source_type="payment_reversal", source_id=payment_id)
    assert lines["1100"]["debit"] == Decimal("30.00")
    assert lines["1000"]["credit"] == Decimal("30.00")


def test_ship_order_posts_product_and_packaging_costs(
    db, make_product, make_sales_order
):
    from app.services.inventory_service import get_or_create_default_location
    from app.services.sales_order_service import ship_order

    fg = make_product(
        item_type="finished_good",
        cost_method="standard",
        standard_cost=Decimal("8.00"),
    )
    box = make_product(
        item_type="packaging",
        unit="EA",
        cost_method="average",
        average_cost=Decimal("1.50"),
    )

    bom = BOM(product_id=fg.id, name=f"BOM-SHIP-{fg.id}", active=True)
    db.add(bom)
    db.flush()
    db.add(
        BOMLine(
            bom_id=bom.id,
            component_id=box.id,
            quantity=Decimal("1.00"),
            unit="EA",
            consume_stage="shipping",
            sequence=10,
        )
    )

    location = get_or_create_default_location(db)
    db.add_all(
        [
            Inventory(
                product_id=fg.id,
                location_id=location.id,
                on_hand_quantity=Decimal("10.00"),
                allocated_quantity=Decimal("0"),
            ),
            Inventory(
                product_id=box.id,
                location_id=location.id,
                on_hand_quantity=Decimal("10.00"),
                allocated_quantity=Decimal("0"),
            ),
        ]
    )

    order = make_sales_order(
        product_id=fg.id,
        quantity=2,
        unit_price=Decimal("20.00"),
        status="ready_to_ship",
        shipping_address_line1="123 Test St",
        shipping_city="Bluffton",
        shipping_state="IN",
        shipping_zip="46714",
    )
    db.add(
        SalesOrderLine(
            sales_order_id=order.id,
            product_id=fg.id,
            quantity=Decimal("2.00"),
            unit_price=Decimal("20.00"),
            total=Decimal("40.00"),
            line_type="product",
        )
    )
    db.flush()

    for account in db.query(GLAccount).filter(
        GLAccount.account_code.in_(["1220", "1230", "5000", "5010"])
    ).all():
        account.account_code = f"OLD-{account.account_code}-{order.id}"[:20]
    db.flush()

    ship_order(
        db,
        order.id,
        user_id=1,
        user_email="admin@example.com",
        tracking_number="TESTTRACK",
    )

    lines = _entry_lines(db, source_type="sales_order", source_id=order.id)
    linked_txn_count = (
        db.query(InventoryTransaction)
        .filter(
            InventoryTransaction.reference_type == "sales_order",
            InventoryTransaction.reference_id == order.id,
            InventoryTransaction.journal_entry_id.isnot(None),
        )
        .count()
    )

    assert lines["5000"]["debit"] == Decimal("16.00")
    assert lines["1220"]["credit"] == Decimal("16.00")
    assert lines["5010"]["debit"] == Decimal("3.00")
    assert lines["1230"]["credit"] == Decimal("3.00")
    assert linked_txn_count == 2


def test_shipment_gl_entry_rejects_unexpected_transaction_type(
    db, make_product, make_sales_order
):
    from app.services.inventory_service import get_or_create_default_location
    from app.services.sales_order_service import _create_shipment_gl_entry

    product = make_product(
        item_type="finished_good",
        cost_method="standard",
        standard_cost=Decimal("8.00"),
    )
    order = make_sales_order(
        product_id=product.id,
        quantity=1,
        unit_price=Decimal("20.00"),
        status="ready_to_ship",
    )
    location = get_or_create_default_location(db)
    txn = InventoryTransaction(
        product_id=product.id,
        location_id=location.id,
        transaction_type="adjustment",
        reference_type="sales_order",
        reference_id=order.id,
        quantity=Decimal("-1.00"),
        cost_per_unit=Decimal("8.00"),
        total_cost=Decimal("8.00"),
    )
    db.add(txn)
    db.flush()

    with pytest.raises(ValueError, match="Unexpected shipment transaction types"):
        _create_shipment_gl_entry(db, order, user_id=1, shipment_transactions=[txn])


def test_shipment_gl_entry_rejects_material_backed_order_lines(
    db, make_sales_order
):
    from app.services.sales_order_service import _create_shipment_gl_entry

    order = make_sales_order(
        quantity=1,
        unit_price=Decimal("20.00"),
        status="ready_to_ship",
    )
    material_type = MaterialType(
        code=f"CR-MT-{order.id}",
        name=f"CodeRabbit Material {order.id}",
        base_material="PLA",
        density=Decimal("1.2400"),
        base_price_per_kg=Decimal("20.00"),
    )
    color = Color(
        code=f"CR-C-{order.id}",
        name=f"CodeRabbit Color {order.id}",
        hex_code="#000000",
    )
    db.add_all([material_type, color])
    db.flush()
    material = MaterialInventory(
        material_type_id=material_type.id,
        color_id=color.id,
        sku=f"CR-MAT-{order.id}",
        quantity_kg=Decimal("1.000"),
        cost_per_kg=Decimal("20.00"),
    )
    db.add(material)
    db.flush()
    db.add(
        SalesOrderLine(
            sales_order_id=order.id,
            line_type="material",
            material_inventory_id=material.id,
            quantity=Decimal("1.00"),
            unit_price=Decimal("20.00"),
            total=Decimal("20.00"),
        )
    )
    db.flush()

    with pytest.raises(ValueError, match="raw-material account mapping"):
        _create_shipment_gl_entry(db, order, user_id=1, shipment_transactions=[])
