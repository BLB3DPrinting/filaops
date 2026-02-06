"""
Complete Order-to-Ship Test Workflow

This script creates a complete test scenario:
1. Creates items (finished good + materials)
2. Creates BOM
3. Creates vendor
4. Creates purchase order
5. Receives PO (adds inventory)
6. Creates sales order
7. Confirms SO (creates production orders)
8. Shows how to start/complete production
9. Shows how to ship

Run with: python -m scripts.test_order_to_ship_workflow
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from decimal import Decimal

from app.db.session import SessionLocal
from app.models.product import Product
from app.models.item_category import ItemCategory
from app.models.bom import BOM, BOMLine
from app.models.vendor import Vendor
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.user import User
from app.core.security import hash_password
from app.models.production_order import ProductionOrder
from app.models.inventory import Inventory, InventoryTransaction
from app.models.inventory import InventoryLocation
from app.models.payment import Payment
from app.models.work_center import WorkCenter
from app.models.manufacturing import Resource
# Note: Routing imports moved to function to avoid table redefinition error
from app.models.scrap_reason import ScrapReason
from app.models.company_settings import CompanySettings
from sqlalchemy import desc


def get_or_create_category(db: Session, code: str, name: str) -> ItemCategory:
    """Get or create category"""
    cat = db.query(ItemCategory).filter(ItemCategory.code == code).first()
    if not cat:
        cat = ItemCategory(
            code=code,
            name=name,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(cat)
        db.commit()
        db.refresh(cat)
    return cat


def get_or_create_location(db: Session, code: str, name: str) -> InventoryLocation:
    """Get or create location"""
    loc = db.query(InventoryLocation).filter(InventoryLocation.code == code).first()
    if not loc:
        loc = InventoryLocation(
            code=code,
            name=name,
            active=True
        )
        db.add(loc)
        db.commit()
        db.refresh(loc)
    return loc


def create_test_items(db: Session):
    """Create test items: 1 finished good + 2 materials"""
    print("\n" + "="*60)
    print("STEP 1: Creating Test Items")
    print("="*60)
    
    # Get categories
    finished_cat = get_or_create_category(db, "FINISHED_GOODS", "Finished Goods")
    material_cat = get_or_create_category(db, "FILAMENT", "Filament")
    
    # Check if finished good exists
    finished_good = db.query(Product).filter(Product.sku == "TEST-WIDGET-001").first()
    if finished_good:
        print(f"  [SKIP] Finished good already exists: {finished_good.sku} - {finished_good.name}")
    else:
        finished_good = Product(
            sku="TEST-WIDGET-001",
            name="Test Widget",
            description="Test finished good product for workflow testing",
            category_id=finished_cat.id,
            item_type="finished_good",
            procurement_type="make",
            standard_cost=Decimal("5.00"),
            selling_price=Decimal("25.00"),
            unit="EA",
            active=True,
            has_bom=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(finished_good)
        db.flush()
        print(f"  [OK] Created finished good: {finished_good.sku} - {finished_good.name}")
    
    # Check if material1 exists
    material1 = db.query(Product).filter(Product.sku == "TEST-PLA-BLACK").first()
    if material1:
        print(f"  [SKIP] Material already exists: {material1.sku} - {material1.name}")
    else:
        material1 = Product(
            sku="TEST-PLA-BLACK",
            name="Test PLA Filament - Black",
            description="Test material for workflow",
            category_id=material_cat.id,
            item_type="raw_material",
            procurement_type="buy",
            standard_cost=Decimal("20.00"),
            selling_price=Decimal("25.00"),
            unit="KG",
            active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(material1)
        db.flush()
        print(f"  [OK] Created material: {material1.sku} - {material1.name}")
    
    # Check if material2 exists
    material2 = db.query(Product).filter(Product.sku == "TEST-PACKAGING-BOX").first()
    if material2:
        print(f"  [SKIP] Material already exists: {material2.sku} - {material2.name}")
    else:
        material2 = Product(
            sku="TEST-PACKAGING-BOX",
            name="Test Packaging Box",
            description="Test packaging material",
            category_id=material_cat.id,
            item_type="raw_material",
            procurement_type="buy",
            standard_cost=Decimal("2.00"),
            selling_price=Decimal("3.00"),
            unit="EA",
            active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(material2)
        db.flush()
        print(f"  [OK] Created material: {material2.sku} - {material2.name}")
    
    db.commit()
    return finished_good, material1, material2


def create_bom(db: Session, finished_good: Product, material1: Product, material2: Product):
    """Create BOM for finished good"""
    print("\n" + "="*60)
    print("STEP 2: Creating BOM")
    print("="*60)
    
    # Check if BOM already exists
    bom = db.query(BOM).filter(
        BOM.product_id == finished_good.id,
        BOM.active == True
    ).first()
    
    if bom:
        print(f"  [SKIP] BOM already exists for {finished_good.sku}")
        # Check if lines exist
        lines = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).all()
        if lines:
            print(f"       Found {len(lines)} BOM lines")
            return bom
    else:
        bom = BOM(
            product_id=finished_good.id,
            version=1,
            active=True,
            name="Test BOM",
            notes="Test BOM for workflow",
            created_at=datetime.utcnow()
        )
        db.add(bom)
        db.flush()
    
    # Check/add components
    comp1 = db.query(BOMLine).filter(
        BOMLine.bom_id == bom.id,
        BOMLine.component_id == material1.id
    ).first()
    if not comp1:
        comp1 = BOMLine(
            bom_id=bom.id,
            component_id=material1.id,
            quantity=Decimal("500"),  # 500 grams (0.5 KG) of PLA per widget
            unit="G",  # Use grams, not KG (more realistic for 3D printing)
            sequence=1,
            scrap_factor=Decimal("0.05"),  # 5% scrap
            consume_stage="production"
        )
        db.add(comp1)
        print(f"  [OK] Added BOM line: {comp1.quantity} {comp1.unit} of {material1.sku}")
    else:
        print(f"  [SKIP] BOM line already exists: {comp1.quantity} {comp1.unit} of {material1.sku}")
    
    comp2 = db.query(BOMLine).filter(
        BOMLine.bom_id == bom.id,
        BOMLine.component_id == material2.id
    ).first()
    if not comp2:
        comp2 = BOMLine(
            bom_id=bom.id,
            component_id=material2.id,
            quantity=Decimal("1"),  # 1 box
            unit="EA",
            sequence=2,
            scrap_factor=Decimal("0"),
            consume_stage="shipping"  # Packaging consumed at shipping
        )
        db.add(comp2)
        print(f"  [OK] Added BOM line: {comp2.quantity} {comp2.unit} of {material2.sku}")
    else:
        print(f"  [SKIP] BOM line already exists: {comp2.quantity} {comp2.unit} of {material2.sku}")
    
    db.commit()
    if bom.id:  # Refresh to get ID if new
        db.refresh(bom)
    
    return bom


def create_vendor(db: Session):
    """Create test vendor"""
    print("\n" + "="*60)
    print("STEP 3: Creating Vendor")
    print("="*60)
    
    vendor = db.query(Vendor).filter(Vendor.code == "TEST-SUPPLIER").first()
    if vendor:
        print(f"  [SKIP] Vendor already exists: {vendor.name} ({vendor.code})")
    else:
        vendor = Vendor(
            name="Test Supplier Co",
            code="TEST-SUPPLIER",
            email="supplier@test.com",
            phone="555-0100",
            address_line1="123 Test St",
            city="Test City",
            state="TS",
            postal_code="12345",
            country="USA",
            payment_terms="Net 30",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(vendor)
        db.commit()
        db.refresh(vendor)
        print(f"  [OK] Created vendor: {vendor.name} ({vendor.code})")
    
    return vendor


def create_purchase_order(db: Session, vendor: Vendor, material1: Product, material2: Product):
    """Create purchase order for materials"""
    print("\n" + "="*60)
    print("STEP 4: Creating Purchase Order")
    print("="*60)
    
    po = PurchaseOrder(
        po_number=f"PO-TEST-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        vendor_id=vendor.id,
        order_date=datetime.utcnow().date(),
        expected_date=(datetime.utcnow() + timedelta(days=7)).date(),
        status="draft",
        total_amount=Decimal("0"),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(po)
    db.flush()
    
    # Add lines
    line1_qty = Decimal("10")  # 10 KG
    line1_price = Decimal("20.00")
    line1 = PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=material1.id,
        quantity_ordered=line1_qty,
        unit_cost=line1_price,
        line_total=line1_qty * line1_price,
        line_number=1
    )
    db.add(line1)
    
    line2_qty = Decimal("5")  # 5 boxes
    line2_price = Decimal("2.00")
    line2 = PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=material2.id,
        quantity_ordered=line2_qty,
        unit_cost=line2_price,
        line_total=line2_qty * line2_price,
        line_number=2
    )
    db.add(line2)
    
    po.total_amount = line1.line_total + line2.line_total
    
    db.commit()
    db.refresh(po)
    print(f"  [OK] Created PO: {po.po_number}")
    print(f"       Status: {po.status}")
    print(f"       Total: ${po.total_amount}")
    print(f"       Lines: {len(po.lines)}")
    
    return po


def receive_purchase_order(db: Session, po: PurchaseOrder):
    """Receive purchase order (adds inventory)"""
    print("\n" + "="*60)
    print("STEP 5: Receiving Purchase Order")
    print("="*60)
    
    # Get default location
    location = db.query(InventoryLocation).filter(InventoryLocation.code == "MAIN").first()
    if not location:
        location = InventoryLocation(
            code="MAIN",
            name="Main Warehouse",
            active=True
        )
        db.add(location)
        db.commit()
        db.refresh(location)
    
    # Receive each line
    for line in po.lines:
        line.quantity_received = line.quantity_ordered
        
        # Add inventory
        inventory = db.query(Inventory).filter(
            Inventory.product_id == line.product_id,
            Inventory.location_id == location.id
        ).first()
        
        if inventory:
            inventory.on_hand_quantity += line.quantity_received
            inventory.updated_at = datetime.utcnow()
        else:
            inventory = Inventory(
                product_id=line.product_id,
                location_id=location.id,
                on_hand_quantity=line.quantity_received,
                allocated_quantity=Decimal("0"),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(inventory)
        
        # Create inventory transaction
        txn = InventoryTransaction(
            product_id=line.product_id,
            location_id=location.id,
            transaction_type="receipt",
            reference_type="purchase_order",
            reference_id=po.id,
            quantity=line.quantity_received,
            cost_per_unit=line.unit_cost,
            notes=f"Received from PO {po.po_number}",
            created_by="system",
            created_at=datetime.utcnow()
        )
        db.add(txn)
        
        print(f"  [OK] Received {line.quantity_received} {line.product.unit} of {line.product.sku}")
        print(f"       Inventory: {inventory.on_hand_quantity} {line.product.unit} on-hand")
        print(f"       Transaction: {txn.transaction_type} created")
    
    po.status = "received"
    po.received_date = datetime.utcnow().date()
    
    db.commit()
    print(f"\n  [OK] PO {po.po_number} fully received")
    
    return location


def generate_customer_number(db: Session) -> str:
    """Generate next customer number in format CUST-001"""
    last_user = (
        db.query(User)
        .filter(User.customer_number.isnot(None))
        .order_by(desc(User.customer_number))
        .first()
    )
    
    if last_user and last_user.customer_number:
        try:
            last_num = int(last_user.customer_number.split("-")[1])
            next_num = last_num + 1
        except (ValueError, IndexError):
            next_num = 1
    else:
        next_num = 1
    
    return f"CUST-{next_num:03d}"


def get_or_create_test_user(db: Session):
    """Get or create test user for sales order"""
    user = db.query(User).filter(User.email == "test-customer@test.com").first()
    if not user:
        customer_number = generate_customer_number(db)
        user = User(
            email="test-customer@test.com",
            password_hash=hash_password("test123"),
            customer_number=customer_number,
            first_name="Test",
            last_name="Customer",
            company_name="Test Company",
            phone="555-0100",
            # Billing address
            billing_address_line1="123 Test Street",
            billing_city="Test City",
            billing_state="TS",
            billing_zip="12345",
            billing_country="USA",
            # Shipping address
            shipping_address_line1="123 Test Street",
            shipping_city="Test City",
            shipping_state="TS",
            shipping_zip="12345",
            shipping_country="USA",
            email_verified=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"  [OK] Created test user: {user.email}")
        print(f"       Customer Number: {user.customer_number}")
        print(f"       Address: {user.shipping_address_line1}, {user.shipping_city}, {user.shipping_state} {user.shipping_zip}")
    else:
        print(f"  [SKIP] Test user already exists: {user.email}")
        if not user.customer_number:
            user.customer_number = generate_customer_number(db)
            db.commit()
            print(f"       Assigned Customer Number: {user.customer_number}")
    return user


def create_sales_order(db: Session, finished_good: Product):
    """Create sales order"""
    print("\n" + "="*60)
    print("STEP 6: Creating Sales Order")
    print("="*60)
    
    # Get or create test user
    user = get_or_create_test_user(db)
    
    # Create sales order with line_item type
    order_number = f"SO-TEST-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    line_qty = Decimal("3")
    line_price = Decimal("25.00")
    line_total = line_qty * line_price
    
    so = SalesOrder(
        order_number=order_number,
        user_id=user.id,
        order_type="line_item",
        source="manual",
        status="draft",
        quantity=3,  # Required field
        material_type="PLA",  # Required field
        finish="standard",  # Required field
        unit_price=line_price,  # Required field
        total_price=line_total,  # Required field
        grand_total=line_total,  # Required field
        payment_status="pending",  # Will be set to paid after payment record created
        fulfillment_status="pending",
        # Shipping address (copy from user)
        shipping_address_line1=user.shipping_address_line1 or "123 Test Street",
        shipping_city=user.shipping_city or "Test City",
        shipping_state=user.shipping_state or "TS",
        shipping_zip=user.shipping_zip or "12345",
        shipping_country=user.shipping_country or "USA",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(so)
    db.flush()
    
    # Add line
    line = SalesOrderLine(
        sales_order_id=so.id,
        product_id=finished_good.id,
        quantity=line_qty,
        unit_price=line_price,
        total=line_total
    )
    db.add(line)
    
    db.commit()
    db.refresh(so)
    print(f"  [OK] Created SO: {so.order_number}")
    print(f"       Status: {so.status}")
    print(f"       Quantity: {line.quantity} {finished_good.sku}")
    print(f"       Total: ${so.grand_total}")
    
    return so


def create_payment_record(db: Session, so: SalesOrder):
    """Create payment record for sales order"""
    print("\n" + "="*60)
    print("STEP 7: Creating Payment Record")
    print("="*60)
    
    # Generate payment number
    last_payment = db.query(Payment).order_by(desc(Payment.payment_number)).first()
    if last_payment and last_payment.payment_number:
        try:
            # Format: PAY-2025-0001
            parts = last_payment.payment_number.split("-")
            if len(parts) == 3:
                year = parts[1]
                num = int(parts[2])
                next_num = num + 1
            else:
                year = datetime.now().strftime("%Y")
                next_num = 1
        except (ValueError, IndexError):
            year = datetime.now().strftime("%Y")
            next_num = 1
    else:
        year = datetime.now().strftime("%Y")
        next_num = 1
    
    payment_number = f"PAY-{year}-{next_num:04d}"
    
    payment = Payment(
        payment_number=payment_number,
        sales_order_id=so.id,
        amount=so.grand_total,
        payment_method="cash",
        payment_type="payment",
        status="completed",
        payment_date=datetime.utcnow(),
        notes="Test payment for workflow",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(payment)
    
    # Update sales order payment status
    so.payment_status = "paid"
    so.paid_at = datetime.utcnow()
    
    db.commit()
    print(f"  [OK] Created payment: {payment.payment_number}")
    print(f"       Amount: ${payment.amount}")
    print(f"       Method: {payment.payment_method}")
    
    return payment


def create_work_centers_and_routings(db: Session, finished_good: Product):
    """Create work centers and routing for production"""
    print("\n" + "="*60)
    print("STEP 8: Creating Work Centers and Routing")
    print("="*60)
    
    # Create work center
    wc = db.query(WorkCenter).filter(WorkCenter.code == "TEST-PRINTER-POOL").first()
    if not wc:
        wc = WorkCenter(
            code="TEST-PRINTER-POOL",
            name="Test 3D Printer Pool",
            description="Test work center for 3D printing",
            center_type="machine",  # Use "machine" so it appears in work center dropdowns
            capacity_hours_per_day=Decimal("16"),
            hourly_rate=Decimal("25.00"),
            machine_rate_per_hour=Decimal("20.00"),
            labor_rate_per_hour=Decimal("5.00"),
            is_active=True,
            active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(wc)
        db.commit()
        db.refresh(wc)
        print(f"  [OK] Created work center: {wc.name}")
    else:
        print(f"  [SKIP] Work center already exists: {wc.name}")
    
    # Create a test resource/machine for the work center
    resource = db.query(Resource).filter(
        Resource.work_center_id == wc.id,
        Resource.code == "TEST-PRINTER-001"
    ).first()
    
    if not resource:
        resource = Resource(
            work_center_id=wc.id,
            code="TEST-PRINTER-001",
            name="Test 3D Printer 001",
            machine_type="X1C",
            status="available",
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(resource)
        db.commit()
        print(f"  [OK] Created resource: {resource.name} ({resource.code})")
    else:
        print(f"  [SKIP] Resource already exists: {resource.name}")
    
    # Try to create routing (may fail due to import issues, but that's OK)
    routing = None
    try:
        # Import Routing here to avoid table redefinition error
        from app.models.manufacturing import Routing, RoutingOperation
        
        # Create routing for finished good
        routing = db.query(Routing).filter(
            Routing.product_id == finished_good.id,
            Routing.active == True
        ).first()
        
        if not routing:
            routing = Routing(
                product_id=finished_good.id,
                name="Test Print Routing",
                description="Test routing for widget production",
                active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(routing)
            db.flush()
            
            # Add operation
            operation = RoutingOperation(
                routing_id=routing.id,
                work_center_id=wc.id,
                operation_name="3D Print",
                sequence=1,
                setup_minutes=5,
                run_minutes_per_unit=Decimal("30"),  # 30 minutes per widget
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(operation)
            db.commit()
            print(f"  [OK] Created routing: {routing.name}")
            print(f"       Operation: {operation.operation_name} ({operation.run_minutes_per_unit} min/unit)")
        else:
            print(f"  [SKIP] Routing already exists for {finished_good.sku}")
    except Exception as e:
        print(f"  [WARN] Could not create routing (this is OK): {e}")
        print(f"         Routing is optional - production orders can still be created without it")
        db.rollback()
    
    return wc, routing


def create_scrap_reasons(db: Session):
    """Create default scrap reason codes"""
    print("\n" + "="*60)
    print("STEP 9: Creating Scrap Reason Codes")
    print("="*60)
    
    reasons = [
        {"code": "adhesion", "name": "Bed Adhesion Failure", "description": "Print failed to adhere to build plate", "sequence": 1},
        {"code": "layer_shift", "name": "Layer Shift", "description": "Layer shift during print", "sequence": 2},
        {"code": "spaghetti", "name": "Spaghetti Failure", "description": "Print detached from bed mid-print", "sequence": 3},
        {"code": "warping", "name": "Warping", "description": "Part warped during print", "sequence": 4},
        {"code": "support_failure", "name": "Support Failure", "description": "Support structures failed", "sequence": 5},
        {"code": "quality", "name": "Quality Issue", "description": "Print quality did not meet standards", "sequence": 6},
    ]
    
    created = 0
    for reason_data in reasons:
        existing = db.query(ScrapReason).filter(ScrapReason.code == reason_data["code"]).first()
        if not existing:
            reason = ScrapReason(
                code=reason_data["code"],
                name=reason_data["name"],
                description=reason_data["description"],
                sequence=reason_data["sequence"],
                active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(reason)
            created += 1
            print(f"  [OK] Created scrap reason: {reason.name}")
        else:
            print(f"  [SKIP] Scrap reason already exists: {reason_data['name']}")
    
    db.commit()
    print(f"\n  [OK] Created {created} scrap reasons")
    
    return created


def create_company_settings(db: Session):
    """Create company settings for tax and business info"""
    print("\n" + "="*60)
    print("STEP 10: Creating Company Settings")
    print("="*60)
    
    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    if not settings:
        settings = CompanySettings(
            id=1,
            company_name="Test Manufacturing Co",
            company_address_line1="123 Manufacturing St",
            company_city="Test City",
            company_state="TS",
            company_zip="12345",
            company_country="USA",
            company_phone="555-0200",
            company_email="info@testmfg.com",
            company_website="https://testmfg.com",
            tax_enabled=True,
            tax_rate=Decimal("0.0825"),  # 8.25% tax rate
            tax_name="Sales Tax",
            tax_registration_number="TAX-12345",
            default_quote_validity_days=30,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(settings)
        db.commit()
        print(f"  [OK] Created company settings")
        print(f"       Company: {settings.company_name}")
        print(f"       Tax Rate: {float(settings.tax_rate) * 100:.2f}%")
    else:
        print(f"  [SKIP] Company settings already exist")
        if not settings.company_name:
            settings.company_name = "Test Manufacturing Co"
            settings.tax_enabled = True
            settings.tax_rate = Decimal("0.0825")
            db.commit()
            print(f"       Updated company settings")
    
    return settings


def confirm_sales_order(db: Session, so: SalesOrder):
    """Confirm sales order (creates production orders)"""
    print("\n" + "="*60)
    print("STEP 11: Confirming Sales Order (Creates Production Orders)")
    print("="*60)
    
    so.status = "confirmed"
    so.confirmed_at = datetime.utcnow()
    
    # Create production orders for each line
    line_num = 1
    for line in so.lines:
        # Get active BOM
        bom = db.query(BOM).filter(
            BOM.product_id == line.product_id,
            BOM.active == True
        ).first()
        
        if bom:
            # Get routing if exists (try to import, but routing is optional)
            routing_id = None
            try:
                from app.models.manufacturing import Routing
                routing = db.query(Routing).filter(
                    Routing.product_id == line.product_id,
                    Routing.active == True
                ).first()
                routing_id = routing.id if routing else None
            except Exception:
                # Routing import failed or doesn't exist - that's OK
                pass
            
            po = ProductionOrder(
                code=f"WO-{so.order_number}-{line_num}",
                product_id=line.product_id,
                bom_id=bom.id,
                routing_id=routing_id,
                sales_order_id=so.id,
                sales_order_line_id=line.id,
                quantity_ordered=line.quantity,
                quantity_completed=Decimal("0"),
                quantity_scrapped=Decimal("0"),
                source="sales_order",
                status="released",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(po)
            print(f"  [OK] Created Production Order: {po.code}")
            print(f"       Status: {po.status}")
            print(f"       Quantity: {po.quantity_ordered}")
            line_num += 1
    
    db.commit()
    print(f"\n  [OK] Sales Order {so.order_number} confirmed")
    print(f"       Production orders created and ready to schedule")
    
    return so


def print_summary(db: Session):
    """Print workflow summary"""
    print("\n" + "="*60)
    print("WORKFLOW SUMMARY")
    print("="*60)
    
    items = db.query(Product).filter(Product.sku.like("TEST-%")).all()
    print(f"\nItems Created: {len(items)}")
    for item in items:
        print(f"  - {item.sku}: {item.name} ({item.item_type})")
    
    pos = db.query(PurchaseOrder).filter(PurchaseOrder.po_number.like("PO-TEST-%")).all()
    print(f"\nPurchase Orders: {len(pos)}")
    for po in pos:
        print(f"  - {po.po_number}: {po.status} (${po.total_amount})")
    
    sos = db.query(SalesOrder).filter(SalesOrder.order_number.like("SO-TEST-%")).all()
    print(f"\nSales Orders: {len(sos)}")
    for so in sos:
        print(f"  - {so.order_number}: {so.status} (${so.grand_total})")
        pos = db.query(ProductionOrder).filter(ProductionOrder.sales_order_id == so.id).all()
        print(f"    Production Orders: {len(pos)}")
        for po in pos:
            print(f"      - {po.code}: {po.status}")
    
    print("\n" + "="*60)
    print("NEXT STEPS TO TEST:")
    print("="*60)
    print("1. Schedule Production Orders (assign to work center/resource)")
    print("2. Start Production (reserves materials, creates print jobs)")
    print("3. Complete Production (consumes materials, adds finished goods)")
    print("4. Ship Sales Order (consumes packaging materials)")
    print("\nUse the API endpoints or frontend to continue the workflow!")


def main():
    """Run complete test workflow"""
    print("\n" + "="*60)
    print("ORDER-TO-SHIP TEST WORKFLOW")
    print("="*60)
    print("\nThis script creates a complete test scenario:")
    print("  - Items (finished good + materials)")
    print("  - BOM")
    print("  - Vendor")
    print("  - Purchase Order")
    print("  - Receive PO (adds inventory)")
    print("  - Sales Order")
    print("  - Confirm SO (creates production orders)")
    print("\nReady to start? (Press Enter to continue or Ctrl+C to cancel)")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\nCancelled.")
        return
    
    db: Session = SessionLocal()
    
    try:
        # Step 1: Create items
        finished_good, material1, material2 = create_test_items(db)
        
        # Step 2: Create BOM
        bom = create_bom(db, finished_good, material1, material2)
        
        # Step 3: Create vendor
        vendor = create_vendor(db)
        
        # Step 4: Create purchase order
        po = create_purchase_order(db, vendor, material1, material2)
        
        # Step 5: Receive PO (only receive the latest one, skip if others already received)
        # Check if there are other draft POs - only receive the latest one
        draft_pos = db.query(PurchaseOrder).filter(
            PurchaseOrder.po_number.like("PO-TEST-%"),
            PurchaseOrder.status == "draft"
        ).order_by(desc(PurchaseOrder.created_at)).all()
        
        if len(draft_pos) > 1:
            print(f"\n  [INFO] Found {len(draft_pos)} draft POs. Only receiving the latest one.")
            # Only receive the most recent one
            po_to_receive = draft_pos[0]
            location = receive_purchase_order(db, po_to_receive)
        else:
            location = receive_purchase_order(db, po)
        
        # Step 6: Create sales order
        so = create_sales_order(db, finished_good)
        
        # Step 7: Create payment record
        payment = create_payment_record(db, so)
        
        # Step 8: Create work centers and routings
        wc, routing = create_work_centers_and_routings(db, finished_good)
        
        # Step 9: Create scrap reasons
        create_scrap_reasons(db)
        
        # Step 10: Create company settings
        create_company_settings(db)
        
        # Step 11: Confirm SO (creates production orders)
        so = confirm_sales_order(db, so)
        
        # Print summary
        print_summary(db)
        
        print("\n" + "="*60)
        print("[OK] Test workflow setup complete!")
        print("="*60)
        print("\nYou can now test:")
        print("  - Scheduling production orders")
        print("  - Starting production")
        print("  - Completing production")
        print("  - Shipping orders")
        print("\nCheck the frontend or use API endpoints to continue!")
        
    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] Workflow failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

