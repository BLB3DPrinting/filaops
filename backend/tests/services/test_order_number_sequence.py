"""Sales order number allocation (ORD-C01 and the PR #973 review).

- Numeric ordering past 999, mixed widths, and suffixes that are not numbers.
- The quote conversion paths use the shared allocator.
- Concurrent allocations wait on the per-year advisory lock. That includes
  the first order of a year, when there is no existing row to lock.
"""
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.quote import Quote
from app.models.sales_order import SalesOrder
from app.services import quote_service
from app.services.quote_conversion_service import generate_sales_order_number
from app.services.sales_order_service import (
    _ORDER_NUMBER_LOCK_NAMESPACE,
    generate_order_number,
)


def _year():
    return datetime.now(timezone.utc).year


def _seq(order_number):
    return int(order_number.rsplit("-", 1)[1])


def test_order_number_sequence_crossing_1000(db, make_sales_order):
    """Verify order number generation does not duplicate when crossing #999 to #1000."""
    year = _year()

    # Seed order 999
    make_sales_order(order_number=f"SO-{year}-999")

    # Next order should be 1000
    next_order_num = generate_order_number(db)
    assert next_order_num == f"SO-{year}-1000"

    # Seed order 1000
    make_sales_order(order_number=next_order_num)

    # Next order should be 1001 (not 1000 again)
    next_order_num_2 = generate_order_number(db)
    assert next_order_num_2 == f"SO-{year}-1001"


def test_order_number_uses_numeric_not_text_max(db, make_sales_order):
    """As text, SO-YYYY-999 sorts after SO-YYYY-1000. The numeric max wins."""
    year = _year()
    make_sales_order(order_number=f"SO-{year}-1000")
    make_sales_order(order_number=f"SO-{year}-999")
    make_sales_order(order_number=f"SO-{year}-0042")

    assert generate_order_number(db) == f"SO-{year}-1001"


def test_order_number_ignores_suffixes_that_are_not_numbers(db, make_sales_order):
    """Rows like SO-YYYY-9999-A must not break the numeric cast."""
    year = _year()
    make_sales_order(order_number=f"SO-{year}-5000")
    make_sales_order(order_number=f"SO-{year}-9999-A")
    make_sales_order(order_number=f"SO-{year}-X12")

    assert generate_order_number(db) == f"SO-{year}-5001"


def test_width_pads_the_sequence(db):
    year = _year()
    next_seq = _seq(generate_order_number(db))
    assert generate_order_number(db, width=6) == f"SO-{year}-{next_seq:06d}"


def test_portal_quote_conversion_uses_shared_allocator(db, make_sales_order):
    """quote_conversion_service used to sort as text and repeat 1000."""
    year = _year()
    make_sales_order(order_number=f"SO-{year}-1000")
    make_sales_order(order_number=f"SO-{year}-999")

    assert generate_sales_order_number(db) == f"SO-{year}-1001"


def test_admin_quote_conversion_uses_shared_allocator(db, make_sales_order):
    """quote_service's own query cast every suffix and failed on SO-YYYY-12-B."""
    year = _year()
    make_sales_order(order_number=f"SO-{year}-1999")
    make_sales_order(order_number=f"SO-{year}-12-B")
    now = datetime.now(timezone.utc)
    quote = Quote(
        quote_number=f"Q-SEQ-{now.strftime('%H%M%S%f')}",
        user_id=1,
        product_name="Sequence Widget",
        quantity=1,
        unit_price=Decimal("10.00"),
        subtotal=Decimal("10.00"),
        total_price=Decimal("10.00"),
        material_type="PLA",
        status="approved",
        file_format="manual",
        file_size_bytes=0,
        expires_at=now + timedelta(days=30),
        created_at=now,
        updated_at=now,
    )
    db.add(quote)
    db.flush()

    result = quote_service.convert_quote_to_order(db, quote.id)

    assert result["order_number"] == f"SO-{year}-2000"


def _lock_waiters(conn, year):
    return conn.execute(
        text(
            """
            SELECT count(*) FROM pg_locks
            WHERE locktype = 'advisory'
              AND NOT granted
              AND classid::bigint = :namespace
              AND objid::bigint = :year
              AND objsubid = 2
            """
        ),
        {"namespace": _ORDER_NUMBER_LOCK_NAMESPACE, "year": year},
    ).scalar()


def test_concurrent_allocations_wait_for_the_first_to_commit():
    """Two transactions allocating at once get different numbers.

    Transaction A allocates and holds the lock. Transaction B then allocates
    in another thread and must block until A commits its order, then see it.
    In the test database the current year normally has no committed orders,
    so this is the first-of-year case that row locks could not cover.

    This test commits one real row, so it uses its own connections and
    deletes that row at the end.
    """
    year = _year()
    conn_a, conn_b, probe = engine.connect(), engine.connect(), engine.connect()
    session_a, session_b = Session(bind=conn_a), Session(bind=conn_b)
    committed_number = None
    result = {}

    def allocate_in_b():
        try:
            result["number"] = generate_order_number(session_b)
        except Exception as exc:  # surfaced by the assertions below
            result["error"] = exc

    worker = threading.Thread(target=allocate_in_b, daemon=True)
    try:
        number_a = generate_order_number(session_a)
        worker.start()

        deadline = time.monotonic() + 10
        while not _lock_waiters(probe, year):
            assert worker.is_alive(), f"second allocation did not wait: {result}"
            assert time.monotonic() < deadline, "second allocation never waited on the lock"
            time.sleep(0.05)
        assert "number" not in result

        session_a.add(SalesOrder(
            order_number=number_a,
            user_id=1,
            product_name="Order number lock test",
            quantity=1,
            material_type="PLA",
            unit_price=Decimal("1.00"),
            total_price=Decimal("1.00"),
            grand_total=Decimal("1.00"),
            status="draft",
        ))
        session_a.commit()
        committed_number = number_a

        worker.join(timeout=10)
        assert not worker.is_alive(), "second allocation still blocked after commit"
        assert "error" not in result, result.get("error")
        assert _seq(result["number"]) == _seq(number_a) + 1
    finally:
        session_a.rollback()  # releases the lock if A never committed
        if worker.ident is not None:
            worker.join(timeout=10)
        session_b.rollback()
        session_a.close()
        session_b.close()
        if committed_number:
            probe.execute(
                text("DELETE FROM sales_orders WHERE order_number = :n"),
                {"n": committed_number},
            )
            probe.commit()
        probe.close()
        conn_a.close()
        conn_b.close()
