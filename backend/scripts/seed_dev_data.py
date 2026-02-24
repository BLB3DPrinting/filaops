"""
Seed Realistic Dev Data for FilaOps UAT
========================================

Creates a complete, realistic dataset for a 3D filament manufacturing business:
- Inventory locations (warehouse hierarchy)
- Work centers & resources (printers)
- Vendors with purchase history
- Customers with contact info
- Raw materials (filament) with proper UOM (G/KG/1000)
- Components (hardware, packaging)
- Finished goods with BOMs and routings
- Sales orders with line items and customers
- Production orders with operations (from routings)
- Inventory levels with transaction history
- Reorder points configured for MRP

Usage:
    cd backend
    python -m scripts.seed_dev_data          # seed only (fails if data already exists)
    python -m scripts.seed_dev_data --reset  # TRUNCATE all data first, then seed (recommended)

Safety:
    - Only runs against the 'filaops' database (dev)
    - Refuses to run against filaops_prod or filaops_test
    - --reset prompts for confirmation before truncating
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import SessionLocal, engine


# ─────────────────────────────────────────────────────────────────────────────
# Safety: verify we're on the dev database
# ─────────────────────────────────────────────────────────────────────────────

def verify_database():
    """Refuse to run against prod or test databases."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT current_database()"))
        db_name = result.scalar()

    if db_name != "filaops":
        print(f"\n  ABORT: Connected to '{db_name}', expected 'filaops' (dev).")
        print("  This script only runs against the dev database.")
        sys.exit(1)

    print(f"  Database: {db_name} (dev) OK")
    return db_name


# ─────────────────────────────────────────────────────────────────────────────
# Reset: truncate all tables in FK-safe order
# ─────────────────────────────────────────────────────────────────────────────

TRUNCATE_ORDER = [
    # Deepest children first (no FKs point TO these)
    "production_lot_consumptions",
    "production_order_operation_materials",
    "production_order_operations",
    "production_order_materials",
    "production_order_spools",
    "serial_numbers",
    "material_lots",
    "scrap_records",
    "print_jobs",
    "production_orders",
    "routing_operation_materials",
    "routing_operations",
    "routings",
    "bom_lines",
    "boms",
    "sales_order_lines",
    "order_events",
    "shipping_events",
    "payments",
    "sales_orders",
    "quote_materials",
    "quote_files",
    "quotes",
    "purchase_order_lines",
    "purchase_order_documents",
    "purchasing_events",
    "purchase_orders",
    "vendor_items",
    "inventory_transactions",
    "inventory",
    "material_inventory",
    "material_colors",
    "material_spools",
    "material_types",
    "colors",
    "planned_orders",
    "mrp_runs",
    "maintenance_logs",
    "resources",
    "work_centers",
    "printers",
    "products",
    "item_categories",
    "vendors",
    "customer_traceability_profiles",
    "customers",
    "refresh_tokens",
    "users",
    "gl_journal_entry_lines",
    "gl_journal_entries",
    "gl_fiscal_periods",
    "gl_accounts",
    "units_of_measure",
    "inventory_locations",
    "company_settings",
    "scrap_reasons",
    "adjustment_reasons",
]


def reset_database(db: Session):
    """Truncate all tables. Uses CASCADE to handle any missed FK deps."""
    print("\n  Truncating all tables...")
    for table in TRUNCATE_ORDER:
        try:
            with db.begin_nested():
                db.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        except Exception as e:
            if "does not exist" not in str(e):
                print(f"  WARNING: Failed to truncate {table}: {e}")
    db.commit()
    print("  All tables truncated OK")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

NOW = datetime.now(timezone.utc)
TODAY = date.today()


def days_ago(n):
    return NOW - timedelta(days=n)


def date_ago(n):
    return TODAY - timedelta(days=n)


# ─────────────────────────────────────────────────────────────────────────────
# Seed functions
# ─────────────────────────────────────────────────────────────────────────────

def seed_gl_accounts(db: Session):
    """Core chart of accounts."""
    from app.models.accounting import GLAccount

    accounts = [
        ("1000", "Cash", "asset", True),
        ("1200", "Accounts Receivable", "asset", True),
        ("1210", "WIP Inventory", "asset", True),
        ("1220", "Finished Goods Inventory", "asset", True),
        ("1230", "Packaging Inventory", "asset", True),
        ("1300", "Inventory Asset", "asset", True),
        ("1310", "WIP Inventory (Legacy)", "asset", True),
        ("2000", "Accounts Payable", "liability", True),
        ("3000", "Retained Earnings", "equity", True),
        ("4000", "Sales Revenue", "revenue", True),
        ("5000", "Cost of Goods Sold", "expense", True),
        ("5010", "Shipping Supplies", "expense", True),
        ("5020", "Scrap Expense (Production)", "expense", True),
        ("5100", "Material Cost", "expense", True),
        ("5200", "Scrap Expense", "expense", True),
        ("5500", "Inventory Adjustment", "expense", True),
    ]
    for code, name, acct_type, is_sys in accounts:
        db.add(GLAccount(
            account_code=code, name=name, account_type=acct_type, is_system=is_sys
        ))
    db.flush()
    print("  GL Accounts: 16 created")


def seed_uoms(db: Session):
    """Standard units of measure."""
    from app.models.uom import UnitOfMeasure

    base = [
        ("EA", "Each", "ea", "quantity"),
        ("KG", "Kilogram", "kg", "weight"),
        ("M", "Meter", "m", "length"),
        ("HR", "Hour", "hr", "time"),
    ]
    base_ids = {}
    for code, name, symbol, cls in base:
        u = UnitOfMeasure(
            code=code, name=name, symbol=symbol, uom_class=cls,
            to_base_factor=Decimal("1"), active=True,
        )
        db.add(u)
        db.flush()
        base_ids[code] = u.id

    derived = [
        ("G", "Gram", "g", "weight", "KG", Decimal("0.001")),
        ("LB", "Pound", "lb", "weight", "KG", Decimal("0.453592")),
        ("OZ", "Ounce", "oz", "weight", "KG", Decimal("0.0283495")),
        ("CM", "Centimeter", "cm", "length", "M", Decimal("0.01")),
        ("MM", "Millimeter", "mm", "length", "M", Decimal("0.001")),
        ("FT", "Foot", "ft", "length", "M", Decimal("0.3048")),
        ("IN", "Inch", "in", "length", "M", Decimal("0.0254")),
        ("MIN", "Minute", "min", "time", "HR", Decimal("0.01666667")),
    ]
    for code, name, symbol, cls, base_code, factor in derived:
        db.add(UnitOfMeasure(
            code=code, name=name, symbol=symbol, uom_class=cls,
            base_unit_id=base_ids[base_code], to_base_factor=factor, active=True,
        ))
    db.flush()
    print("  UOMs: 12 created")


def seed_locations(db: Session):
    """Warehouse → shelves → bins hierarchy."""
    from app.models.inventory import InventoryLocation

    wh = InventoryLocation(name="Main Warehouse", code="WH-MAIN", type="warehouse", active=True)
    db.add(wh)
    db.flush()

    shelves = [
        InventoryLocation(name="Raw Materials", code="WH-MAIN-RAW", type="shelf", parent_id=wh.id, active=True),
        InventoryLocation(name="Finished Goods", code="WH-MAIN-FG", type="shelf", parent_id=wh.id, active=True),
        InventoryLocation(name="Packaging & Supplies", code="WH-MAIN-PKG", type="shelf", parent_id=wh.id, active=True),
    ]
    for s in shelves:
        db.add(s)
    db.flush()

    print("  Locations: 4 created (1 warehouse + 3 shelves)")
    return {"warehouse": wh.id}


def seed_admin_user(db: Session):
    """Admin user for dev login."""
    from app.models.user import User
    from app.core.security import hash_password

    admin = User(
        email="admin@filaops.dev",
        password_hash=hash_password("FilaOps2026!"),
        first_name="Admin",
        last_name="User",
        account_type="admin",
        status="active",
        email_verified=True,
    )
    db.add(admin)
    db.flush()
    print("  Admin user: admin@filaops.dev / FilaOps2026!")
    return admin


def seed_customers(db: Session):
    """Realistic B2B customers."""
    from app.models.customer import Customer

    customers_data = [
        {
            "customer_number": "CUST-0001",
            "company_name": "MakerSpace PDX",
            "first_name": "Sarah",
            "last_name": "Chen",
            "email": "sarah@makerspace-pdx.com",
            "phone": "503-555-0101",
            "billing_address_line1": "1420 NW Lovejoy St",
            "billing_city": "Portland",
            "billing_state": "OR",
            "billing_zip": "97209",
            "billing_country": "US",
            "notes": "Bulk filament buyer. Monthly standing order.",
        },
        {
            "customer_number": "CUST-0002",
            "company_name": "Rapid Proto Labs",
            "first_name": "Jake",
            "last_name": "Morrison",
            "email": "jake@rapidprotolabs.com",
            "phone": "206-555-0202",
            "billing_address_line1": "850 Republican St, Suite 300",
            "billing_city": "Seattle",
            "billing_state": "WA",
            "billing_zip": "98109",
            "billing_country": "US",
            "notes": "Engineering prototyping shop. Needs COA on PETG orders.",
        },
        {
            "customer_number": "CUST-0003",
            "company_name": "PrintFarm Co.",
            "first_name": "Maria",
            "last_name": "Gonzalez",
            "email": "maria@printfarm.co",
            "phone": "415-555-0303",
            "billing_address_line1": "200 Kansas St",
            "billing_city": "San Francisco",
            "billing_state": "CA",
            "billing_zip": "94103",
            "billing_country": "US",
            "notes": "Large print farm. 50+ printers. High volume buyer.",
        },
        {
            "customer_number": "CUST-0004",
            "company_name": "DesignWorks Studio",
            "first_name": "Tyler",
            "last_name": "Brooks",
            "email": "tyler@designworks.studio",
            "phone": "720-555-0404",
            "billing_address_line1": "3000 Lawrence St",
            "billing_city": "Denver",
            "billing_state": "CO",
            "billing_zip": "80205",
            "billing_country": "US",
            "shipping_address_line1": "3000 Lawrence St, Dock B",
            "shipping_city": "Denver",
            "shipping_state": "CO",
            "shipping_zip": "80205",
            "shipping_country": "US",
            "notes": "Custom product design and printing. Priority customer.",
        },
        {
            "customer_number": "CUST-0005",
            "company_name": "EduPrint Academy",
            "first_name": "Lisa",
            "last_name": "Park",
            "email": "lisa.park@eduprint.edu",
            "phone": "512-555-0505",
            "billing_address_line1": "1 University Station",
            "billing_city": "Austin",
            "billing_state": "TX",
            "billing_zip": "78712",
            "billing_country": "US",
            "notes": "University makerspace. Net-30 terms. PO required.",
        },
    ]

    objs = []
    for c in customers_data:
        cust = Customer(status="active", **c)
        db.add(cust)
        objs.append(cust)
    db.flush()
    print(f"  Customers: {len(objs)} created")
    return objs


def seed_vendors(db: Session):
    """Filament and supply vendors."""
    from app.models.vendor import Vendor

    vendors_data = [
        {
            "code": "VND-BAMBU",
            "name": "Bambu Lab",
            "contact_name": "Bambu Sales",
            "email": "sales@bambulab.com",
            "website": "https://bambulab.com",
            "payment_terms": "Net 30",
            "lead_time_days": 7,
            "rating": Decimal("4.80"),
        },
        {
            "code": "VND-POLYMAKER",
            "name": "Polymaker",
            "contact_name": "Polymaker Wholesale",
            "email": "wholesale@polymaker.com",
            "website": "https://polymaker.com",
            "payment_terms": "Net 30",
            "lead_time_days": 10,
            "rating": Decimal("4.50"),
        },
        {
            "code": "VND-PROTOPASTA",
            "name": "Proto-Pasta",
            "contact_name": "Alex Thompson",
            "email": "alex@proto-pasta.com",
            "phone": "360-555-7777",
            "address_line1": "12805 NE Airport Way",
            "city": "Vancouver",
            "state": "WA",
            "postal_code": "98682",
            "payment_terms": "Net 15",
            "lead_time_days": 5,
            "rating": Decimal("4.90"),
        },
        {
            "code": "VND-ULINE",
            "name": "Uline",
            "contact_name": "Uline Customer Service",
            "email": "cs@uline.com",
            "website": "https://uline.com",
            "payment_terms": "COD",
            "lead_time_days": 3,
            "rating": Decimal("4.00"),
            "notes": "Packaging and shipping supplies only.",
        },
        {
            "code": "VND-MCMASTER",
            "name": "McMaster-Carr",
            "contact_name": "Order Dept",
            "website": "https://mcmaster.com",
            "payment_terms": "Net 30",
            "lead_time_days": 2,
            "rating": Decimal("5.00"),
            "notes": "Hardware, fasteners, heat-set inserts.",
        },
    ]

    objs = []
    for v in vendors_data:
        vendor = Vendor(is_active=True, **v)
        db.add(vendor)
        objs.append(vendor)
    db.flush()
    print(f"  Vendors: {len(objs)} created")
    return objs


def seed_categories(db: Session):
    """Item categories with hierarchy."""
    from app.models.item_category import ItemCategory

    roots = {
        "FILAMENT": ("Filament", 1),
        "PACKAGING": ("Packaging & Shipping", 2),
        "HARDWARE": ("Hardware & Components", 3),
        "FINISHED_GOODS": ("Finished Goods", 4),
        "SERVICES": ("Services", 5),
    }
    root_objs = {}
    for code, (name, order) in roots.items():
        cat = ItemCategory(code=code, name=name, sort_order=order, is_active=True)
        db.add(cat)
        db.flush()
        root_objs[code] = cat

    children = {
        "PLA": ("PLA Filament", "FILAMENT", 1),
        "PETG": ("PETG Filament", "FILAMENT", 2),
        "ABS": ("ABS Filament", "FILAMENT", 3),
        "TPU": ("TPU Filament", "FILAMENT", 4),
        "SPECIALTY": ("Specialty Filament", "FILAMENT", 5),
        "BOXES": ("Shipping Boxes", "PACKAGING", 1),
        "BAGS": ("Poly Bags", "PACKAGING", 2),
        "LABELS": ("Labels & Tape", "PACKAGING", 3),
        "FASTENERS": ("Fasteners", "HARDWARE", 1),
        "INSERTS": ("Heat-Set Inserts", "HARDWARE", 2),
        "MAGNETS": ("Magnets", "HARDWARE", 3),
        "STANDARD_PRODUCTS": ("Standard Products", "FINISHED_GOODS", 1),
        "CUSTOM_PRODUCTS": ("Custom Products", "FINISHED_GOODS", 2),
    }
    child_objs = {}
    for code, (name, parent_code, order) in children.items():
        cat = ItemCategory(
            code=code, name=name, parent_id=root_objs[parent_code].id,
            sort_order=order, is_active=True,
        )
        db.add(cat)
        db.flush()
        child_objs[code] = cat

    all_cats = {**root_objs, **child_objs}
    print(f"  Categories: {len(all_cats)} created")
    return all_cats


def seed_materials_and_colors(db: Session):
    """Material types and color definitions."""
    from app.models.material import MaterialType, Color, MaterialColor

    types_data = [
        ("PLA_BASIC", "PLA Basic", "PLA", Decimal("1.24"), Decimal("20.00"), Decimal("1.0"), False, 5),
        ("PLA_MATTE", "PLA Matte", "PLA", Decimal("1.24"), Decimal("22.00"), Decimal("1.1"), False, 5),
        ("PLA_SILK", "PLA Silk", "PLA", Decimal("1.24"), Decimal("25.00"), Decimal("1.25"), False, 5),
        ("PLA_CF", "PLA-CF", "PLA", Decimal("1.30"), Decimal("45.00"), Decimal("2.25"), False, 9),
        ("PETG_BASIC", "PETG Basic", "PETG", Decimal("1.27"), Decimal("24.00"), Decimal("1.2"), False, 7),
        ("PETG_HF", "PETG High Flow", "PETG", Decimal("1.27"), Decimal("24.00"), Decimal("1.2"), False, 7),
        ("PETG_CF", "PETG-CF", "PETG", Decimal("1.35"), Decimal("48.00"), Decimal("2.4"), False, 9),
        ("ABS_BASIC", "ABS", "ABS", Decimal("1.04"), Decimal("22.00"), Decimal("1.1"), True, 8),
        ("ASA_BASIC", "ASA", "ASA", Decimal("1.07"), Decimal("28.00"), Decimal("1.4"), True, 8),
        ("TPU_95A", "TPU 95A", "TPU", Decimal("1.20"), Decimal("35.00"), Decimal("1.75"), False, 4),
    ]

    mt_objs = {}
    for i, (code, name, base, density, price, mult, encl, strength) in enumerate(types_data):
        mt = MaterialType(
            code=code, name=name, base_material=base, density=density,
            base_price_per_kg=price, price_multiplier=mult,
            requires_enclosure=encl, strength_rating=strength,
            active=True, is_customer_visible=True, display_order=i + 1,
        )
        db.add(mt)
        db.flush()
        mt_objs[code] = mt

    colors_data = [
        ("BLK", "Black", "#000000", 1),
        ("WHT", "White", "#FFFFFF", 2),
        ("GRY", "Gray", "#808080", 3),
        ("RED", "Red", "#FF0000", 4),
        ("BLU", "Blue", "#0000FF", 5),
        ("GRN", "Green", "#00AA00", 6),
        ("YLW", "Yellow", "#FFD700", 7),
        ("ORG", "Orange", "#FF6600", 8),
        ("PRP", "Purple", "#800080", 9),
        ("PNK", "Pink", "#FF69B4", 10),
        ("CHARCOAL", "Charcoal", "#333333", 11),
        ("NAVY", "Navy Blue", "#001F5B", 12),
    ]

    color_objs = {}
    for code, name, hex_code, order in colors_data:
        c = Color(code=code, name=name, hex_code=hex_code, display_order=order,
                  active=True, is_customer_visible=True)
        db.add(c)
        db.flush()
        color_objs[code] = c

    # Link common material+color combos
    combos = [
        # PLA Basic: all colors
        *[("PLA_BASIC", c) for c in ["BLK", "WHT", "GRY", "RED", "BLU", "GRN", "YLW", "ORG", "PRP", "PNK"]],
        # PLA Matte: neutrals + popular
        *[("PLA_MATTE", c) for c in ["BLK", "WHT", "GRY", "CHARCOAL", "RED", "BLU", "GRN"]],
        # PETG Basic: core colors
        *[("PETG_BASIC", c) for c in ["BLK", "WHT", "GRY", "RED", "BLU", "GRN"]],
        # PETG HF: core colors
        *[("PETG_HF", c) for c in ["BLK", "WHT", "GRY", "RED", "BLU"]],
        # ABS: limited
        *[("ABS_BASIC", c) for c in ["BLK", "WHT", "GRY", "RED"]],
        # ASA: outdoor colors
        *[("ASA_BASIC", c) for c in ["BLK", "WHT", "GRY"]],
        # TPU: limited
        *[("TPU_95A", c) for c in ["BLK", "WHT"]],
    ]
    for mt_code, color_code in combos:
        db.add(MaterialColor(
            material_type_id=mt_objs[mt_code].id,
            color_id=color_objs[color_code].id,
            is_customer_visible=True, active=True,
        ))
    db.flush()

    print(f"  Material Types: {len(mt_objs)} | Colors: {len(color_objs)} | Combos: {len(combos)}")
    return mt_objs, color_objs


def seed_products(db: Session, categories, mt_objs, color_objs, vendors):
    """Create raw materials, components, and finished goods."""
    from app.models.product import Product

    products = {}

    # ── Raw Materials (Filament) ──────────────────────────────────────────
    # These are the spools we buy and consume in production
    filaments = [
        # (sku, name, cat_code, mt_code, color_code, vendor_idx, cost_per_kg, on_hand_g)
        ("MAT-PLA-BLK", "PLA Basic - Black 1KG", "PLA", "PLA_BASIC", "BLK", 0, Decimal("20.00"), 8500),
        ("MAT-PLA-WHT", "PLA Basic - White 1KG", "PLA", "PLA_BASIC", "WHT", 0, Decimal("20.00"), 6200),
        ("MAT-PLA-GRY", "PLA Basic - Gray 1KG", "PLA", "PLA_BASIC", "GRY", 0, Decimal("20.00"), 3800),
        ("MAT-PLA-RED", "PLA Basic - Red 1KG", "PLA", "PLA_BASIC", "RED", 0, Decimal("20.00"), 2400),
        ("MAT-PLA-BLU", "PLA Basic - Blue 1KG", "PLA", "PLA_BASIC", "BLU", 0, Decimal("20.00"), 4100),
        ("MAT-PLAM-BLK", "PLA Matte - Black 1KG", "PLA", "PLA_MATTE", "BLK", 1, Decimal("22.00"), 5600),
        ("MAT-PLAM-WHT", "PLA Matte - White 1KG", "PLA", "PLA_MATTE", "WHT", 1, Decimal("22.00"), 3200),
        ("MAT-PLAM-CHAR", "PLA Matte - Charcoal 1KG", "PLA", "PLA_MATTE", "CHARCOAL", 1, Decimal("22.00"), 2900),
        ("MAT-PETG-BLK", "PETG Basic - Black 1KG", "PETG", "PETG_BASIC", "BLK", 0, Decimal("24.00"), 4200),
        ("MAT-PETG-WHT", "PETG Basic - White 1KG", "PETG", "PETG_BASIC", "WHT", 0, Decimal("24.00"), 2800),
        ("MAT-PETGHF-BLK", "PETG HF - Black 1KG", "PETG", "PETG_HF", "BLK", 0, Decimal("24.00"), 3500),
        ("MAT-ABS-BLK", "ABS - Black 1KG", "ABS", "ABS_BASIC", "BLK", 0, Decimal("22.00"), 2100),
        ("MAT-TPU-BLK", "TPU 95A - Black 1KG", "TPU", "TPU_95A", "BLK", 2, Decimal("35.00"), 1800),
        ("MAT-PLACF-BLK", "PLA-CF - Black 1KG", "SPECIALTY", "PLA_CF", "BLK", 2, Decimal("45.00"), 1200),
    ]

    for sku, name, cat, mt_code, clr_code, vendor_idx, cost_kg, stock_g in filaments:
        # Cost stored as $/KG, inventory tracked in grams
        cost_per_g = cost_kg / 1000
        p = Product(
            sku=sku, name=name,
            item_type="supply",
            category_id=categories[cat].id,
            material_type_id=mt_objs[mt_code].id,
            color_id=color_objs[clr_code].id,
            procurement_type="buy",
            is_raw_material=True,
            unit="G", purchase_uom="KG", purchase_factor=Decimal("1000"),
            cost_method="average",
            average_cost=cost_per_g,
            standard_cost=cost_per_g,
            last_cost=cost_per_g,
            reorder_point=Decimal("2000"),  # 2kg
            safety_stock=Decimal("1000"),   # 1kg
            min_order_qty=Decimal("1"),     # 1 spool (1kg)
            lead_time_days=7,
            stocking_policy="stocked",
            preferred_vendor_id=vendors[vendor_idx].id,
            active=True,
            track_lots=True,
        )
        db.add(p)
        db.flush()
        products[sku] = (p, stock_g)

    # ── Components & Packaging ────────────────────────────────────────────
    components = [
        ("CMP-INSERT-M3", "M3x5x4 Heat-Set Insert", "INSERTS", "component", Decimal("0.12"), 500, 200, 4),
        ("CMP-INSERT-M4", "M4x6x5 Heat-Set Insert", "INSERTS", "component", Decimal("0.18"), 300, 100, 4),
        ("CMP-MAGNET-6x3", "Neodymium Magnet 6x3mm", "MAGNETS", "component", Decimal("0.35"), 200, 50, 4),
        ("CMP-SCREW-M3x8", "M3x8 Socket Head Cap Screw", "FASTENERS", "component", Decimal("0.05"), 1000, 200, 4),
        ("CMP-SCREW-M3x12", "M3x12 Socket Head Cap Screw", "FASTENERS", "component", Decimal("0.06"), 800, 200, 4),
        ("PKG-BOX-SM", "Shipping Box - Small (6x6x4)", "BOXES", "supply", Decimal("0.75"), 120, 50, 3),
        ("PKG-BOX-MD", "Shipping Box - Medium (10x8x6)", "BOXES", "supply", Decimal("1.10"), 80, 30, 3),
        ("PKG-BOX-LG", "Shipping Box - Large (14x12x8)", "BOXES", "supply", Decimal("1.65"), 45, 20, 3),
        ("PKG-BUBBLE", "Bubble Wrap Roll (12in x 30ft)", "BAGS", "supply", Decimal("8.50"), 6, 2, 3),
        ("PKG-BAG-SM", "Poly Bag 6x9in (100pk)", "BAGS", "supply", Decimal("0.04"), 350, 100, 3),
        ("PKG-LABEL-SHIP", "Shipping Label 4x6 (roll 500)", "LABELS", "supply", Decimal("0.03"), 480, 100, 3),
    ]

    for sku, name, cat, itype, cost, stock, reorder, vendor_idx in components:
        p = Product(
            sku=sku, name=name,
            item_type=itype,
            category_id=categories[cat].id,
            procurement_type="buy",
            unit="EA", purchase_uom="EA", purchase_factor=Decimal("1"),
            cost_method="standard",
            standard_cost=cost,
            average_cost=cost,
            last_cost=cost,
            reorder_point=Decimal(str(reorder)),
            min_order_qty=Decimal("1"),
            lead_time_days=3,
            stocking_policy="stocked",
            preferred_vendor_id=vendors[vendor_idx].id,
            active=True,
        )
        db.add(p)
        db.flush()
        products[sku] = (p, stock)

    # ── Finished Goods ────────────────────────────────────────────────────
    finished = [
        ("FG-WALLMOUNT-01", "Headphone Wall Mount", "STANDARD_PRODUCTS", Decimal("3.20"), Decimal("12.99"), 25),
        ("FG-CABLEORG-01", "Cable Management Clip (5-pack)", "STANDARD_PRODUCTS", Decimal("1.80"), Decimal("7.99"), 40),
        ("FG-PLANTER-01", "Self-Watering Planter (Small)", "STANDARD_PRODUCTS", Decimal("4.50"), Decimal("18.99"), 15),
        ("FG-PHONESTD-01", "Adjustable Phone Stand", "STANDARD_PRODUCTS", Decimal("2.90"), Decimal("11.99"), 30),
        ("FG-KEYCAP-SET", "Custom Keycap Set (WASD + ESC)", "CUSTOM_PRODUCTS", Decimal("5.80"), Decimal("24.99"), 8),
        ("FG-LAMPSHD-01", "Geometric Lampshade", "CUSTOM_PRODUCTS", Decimal("8.20"), Decimal("34.99"), 5),
        ("FG-GEARBOX-01", "Planetary Gearbox Demo", "STANDARD_PRODUCTS", Decimal("6.50"), Decimal("29.99"), 10),
        ("FG-ENCLOSURE-01", "Raspberry Pi 5 Enclosure", "STANDARD_PRODUCTS", Decimal("3.80"), Decimal("14.99"), 20),
        ("FG-TOOLORG-01", "Desk Tool Organizer", "STANDARD_PRODUCTS", Decimal("4.10"), Decimal("16.99"), 12),
        ("FG-PETG-BRACKET", "PETG Industrial Bracket", "STANDARD_PRODUCTS", Decimal("5.20"), Decimal("19.99"), 18),
    ]

    for sku, name, cat, cost, price, stock in finished:
        p = Product(
            sku=sku, name=name,
            item_type="finished_good",
            category_id=categories[cat].id,
            procurement_type="make",
            has_bom=True,
            unit="EA", purchase_uom="EA", purchase_factor=Decimal("1"),
            cost_method="standard",
            standard_cost=cost,
            selling_price=price,
            reorder_point=Decimal("5"),
            safety_stock=Decimal("3"),
            stocking_policy="stocked",
            active=True,
            track_serials=True,
        )
        db.add(p)
        db.flush()
        products[sku] = (p, stock)

    print(f"  Products: {len(products)} total ({len(filaments)} filaments, "
          f"{len(components)} components, {len(finished)} finished goods)")
    return products


def seed_work_centers_and_resources(db: Session):
    """Work centers (departments) and individual printers."""
    from app.models.work_center import WorkCenter
    from app.models.manufacturing import Resource

    wcs = {}

    # FDM Printing work center
    wc_fdm = WorkCenter(
        code="WC-FDM", name="FDM Print Farm",
        center_type="machine",
        capacity_hours_per_day=Decimal("20"),
        machine_rate_per_hour=Decimal("2.50"),
        labor_rate_per_hour=Decimal("0.50"),
        overhead_rate_per_hour=Decimal("0.25"),
        is_active=True,
    )
    db.add(wc_fdm)
    wcs["FDM"] = wc_fdm

    wc_post = WorkCenter(
        code="WC-POST", name="Post-Processing",
        center_type="station",
        capacity_hours_per_day=Decimal("8"),
        labor_rate_per_hour=Decimal("25.00"),
        is_active=True,
    )
    db.add(wc_post)
    wcs["POST"] = wc_post

    wc_qc = WorkCenter(
        code="WC-QC", name="Quality Control",
        center_type="station",
        capacity_hours_per_day=Decimal("8"),
        labor_rate_per_hour=Decimal("20.00"),
        is_active=True,
    )
    db.add(wc_qc)
    wcs["QC"] = wc_qc

    wc_pack = WorkCenter(
        code="WC-PACK", name="Packing & Shipping",
        center_type="station",
        capacity_hours_per_day=Decimal("8"),
        labor_rate_per_hour=Decimal("18.00"),
        is_active=True,
    )
    db.add(wc_pack)
    wcs["PACK"] = wc_pack

    db.flush()

    # Reset sequence
    db.execute(text(
        "SELECT setval(pg_get_serial_sequence('work_centers', 'id'), "
        "COALESCE((SELECT MAX(id) FROM work_centers), 1))"
    ))

    # Printers as resources under FDM work center
    printers = [
        ("P1S-01", "Bambu P1S #1", "P1S", "available"),
        ("P1S-02", "Bambu P1S #2", "P1S", "available"),
        ("P1S-03", "Bambu P1S #3", "P1S", "busy"),
        ("X1C-01", "Bambu X1C #1", "X1C", "available"),
        ("X1C-02", "Bambu X1C #2", "X1C", "maintenance"),
        ("A1M-01", "Bambu A1 Mini #1", "A1", "available"),
    ]

    resources = []
    for code, name, mtype, status in printers:
        r = Resource(
            work_center_id=wc_fdm.id,
            code=code, name=name,
            machine_type=mtype,
            printer_class="enclosed" if mtype in ("X1C", "P1S") else "open",
            status=status,
            is_active=True,
        )
        db.add(r)
        resources.append(r)
    db.flush()

    print(f"  Work Centers: {len(wcs)} | Printers: {len(resources)}")
    return wcs


def seed_boms(db: Session, products):
    """BOMs for finished goods — real material quantities."""
    from app.models.bom import BOM, BOMLine

    boms = {}

    # Helper to get product and its id
    def pid(sku):
        return products[sku][0].id

    bom_definitions = [
        # (fg_sku, bom_name, lines: [(comp_sku, qty, unit, sequence, consume_stage)])
        ("FG-WALLMOUNT-01", "Headphone Wall Mount BOM v1", [
            ("MAT-PLA-BLK", Decimal("85"), "G", 10, "production"),
            ("CMP-INSERT-M3", Decimal("2"), "EA", 20, "production"),
            ("CMP-SCREW-M3x12", Decimal("2"), "EA", 30, "production"),
            ("PKG-BOX-SM", Decimal("1"), "EA", 40, "shipping"),
            ("PKG-BAG-SM", Decimal("1"), "EA", 50, "shipping"),
        ]),
        ("FG-CABLEORG-01", "Cable Clip 5-Pack BOM v1", [
            ("MAT-PLA-BLK", Decimal("35"), "G", 10, "production"),
            ("PKG-BAG-SM", Decimal("1"), "EA", 20, "shipping"),
        ]),
        ("FG-PLANTER-01", "Self-Watering Planter BOM v1", [
            ("MAT-PLAM-WHT", Decimal("120"), "G", 10, "production"),
            ("PKG-BOX-MD", Decimal("1"), "EA", 20, "shipping"),
            ("PKG-BUBBLE", Decimal("1"), "EA", 30, "shipping"),
        ]),
        ("FG-PHONESTD-01", "Phone Stand BOM v1", [
            ("MAT-PLA-GRY", Decimal("65"), "G", 10, "production"),
            ("CMP-INSERT-M3", Decimal("1"), "EA", 20, "production"),
            ("PKG-BOX-SM", Decimal("1"), "EA", 30, "shipping"),
        ]),
        ("FG-KEYCAP-SET", "Keycap Set BOM v1", [
            ("MAT-PLA-RED", Decimal("25"), "G", 10, "production"),
            ("MAT-PLA-BLK", Decimal("15"), "G", 20, "production"),
            ("PKG-BAG-SM", Decimal("1"), "EA", 30, "shipping"),
        ]),
        ("FG-LAMPSHD-01", "Geometric Lampshade BOM v1", [
            ("MAT-PLAM-CHAR", Decimal("180"), "G", 10, "production"),
            ("PKG-BOX-LG", Decimal("1"), "EA", 20, "shipping"),
            ("PKG-BUBBLE", Decimal("1"), "EA", 30, "shipping"),
        ]),
        ("FG-GEARBOX-01", "Planetary Gearbox BOM v1", [
            ("MAT-PLA-BLU", Decimal("95"), "G", 10, "production"),
            ("MAT-PLA-WHT", Decimal("45"), "G", 20, "production"),
            ("PKG-BOX-SM", Decimal("1"), "EA", 30, "shipping"),
        ]),
        ("FG-ENCLOSURE-01", "RPi 5 Enclosure BOM v1", [
            ("MAT-PETG-BLK", Decimal("55"), "G", 10, "production"),
            ("CMP-INSERT-M3", Decimal("4"), "EA", 20, "production"),
            ("CMP-SCREW-M3x8", Decimal("4"), "EA", 30, "production"),
            ("PKG-BOX-SM", Decimal("1"), "EA", 40, "shipping"),
        ]),
        ("FG-TOOLORG-01", "Tool Organizer BOM v1", [
            ("MAT-PLA-BLK", Decimal("110"), "G", 10, "production"),
            ("CMP-MAGNET-6x3", Decimal("4"), "EA", 20, "production"),
            ("PKG-BOX-MD", Decimal("1"), "EA", 30, "shipping"),
        ]),
        ("FG-PETG-BRACKET", "Industrial Bracket BOM v1", [
            ("MAT-PETGHF-BLK", Decimal("75"), "G", 10, "production"),
            ("CMP-INSERT-M4", Decimal("4"), "EA", 20, "production"),
            ("PKG-BOX-SM", Decimal("1"), "EA", 30, "shipping"),
        ]),
    ]

    for fg_sku, bom_name, lines in bom_definitions:
        bom = BOM(
            product_id=pid(fg_sku),
            name=bom_name,
            code=f"BOM-{fg_sku.replace('FG-', '')}",
            version=1, revision="1.0",
            active=True,
        )
        db.add(bom)
        db.flush()

        total_cost = Decimal("0")
        for comp_sku, qty, unit, seq, stage in lines:
            comp = products[comp_sku][0]
            line_cost = qty * (comp.standard_cost or Decimal("0"))
            total_cost += line_cost
            db.add(BOMLine(
                bom_id=bom.id,
                component_id=comp.id,
                quantity=qty,
                unit=unit,
                sequence=seq,
                consume_stage=stage,
            ))

        bom.total_cost = total_cost
        boms[fg_sku] = bom

    db.flush()
    print(f"  BOMs: {len(boms)} created with material lines")
    return boms


def seed_routings(db: Session, products, boms, wcs):
    """Routings (process plans) for finished goods."""
    from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial

    routings = {}

    def pid(sku):
        return products[sku][0].id

    # Define routings: each FG gets a realistic process flow
    routing_defs = [
        # (fg_sku, routing_code, operations: [(seq, op_code, op_name, wc_key, setup_min, run_min, materials)])
        ("FG-WALLMOUNT-01", "RTG-WALLMOUNT", [
            (10, "PRINT", "3D Print Wall Mount", "FDM", 5, 95,
             [("MAT-PLA-BLK", Decimal("85"), "G")]),
            (20, "POST", "Install heat-set inserts", "POST", 2, 5,
             [("CMP-INSERT-M3", Decimal("2"), "EA"), ("CMP-SCREW-M3x12", Decimal("2"), "EA")]),
            (30, "QC", "Visual + fit inspection", "QC", 0, 3, []),
            (40, "PACK", "Package for shipping", "PACK", 1, 4,
             [("PKG-BOX-SM", Decimal("1"), "EA"), ("PKG-BAG-SM", Decimal("1"), "EA")]),
        ]),
        ("FG-CABLEORG-01", "RTG-CABLEORG", [
            (10, "PRINT", "3D Print Cable Clips (5x)", "FDM", 3, 35,
             [("MAT-PLA-BLK", Decimal("35"), "G")]),
            (20, "QC", "Count and inspect clips", "QC", 0, 2, []),
            (30, "PACK", "Bag and label", "PACK", 1, 2,
             [("PKG-BAG-SM", Decimal("1"), "EA")]),
        ]),
        ("FG-PLANTER-01", "RTG-PLANTER", [
            (10, "PRINT", "3D Print Planter Body + Reservoir", "FDM", 5, 180,
             [("MAT-PLAM-WHT", Decimal("120"), "G")]),
            (20, "POST", "Clean support material, sand edges", "POST", 2, 10, []),
            (30, "QC", "Water-tight test + visual", "QC", 0, 5, []),
            (40, "PACK", "Wrap and box", "PACK", 2, 5,
             [("PKG-BOX-MD", Decimal("1"), "EA"), ("PKG-BUBBLE", Decimal("1"), "EA")]),
        ]),
        ("FG-PHONESTD-01", "RTG-PHONESTD", [
            (10, "PRINT", "3D Print Phone Stand", "FDM", 3, 55,
             [("MAT-PLA-GRY", Decimal("65"), "G")]),
            (20, "POST", "Install insert for adjustable hinge", "POST", 1, 3,
             [("CMP-INSERT-M3", Decimal("1"), "EA")]),
            (30, "QC", "Function test (phone fit)", "QC", 0, 2, []),
            (40, "PACK", "Box", "PACK", 1, 3,
             [("PKG-BOX-SM", Decimal("1"), "EA")]),
        ]),
        ("FG-KEYCAP-SET", "RTG-KEYCAP", [
            (10, "PRINT", "Print keycaps (multi-color)", "FDM", 5, 45,
             [("MAT-PLA-RED", Decimal("25"), "G"), ("MAT-PLA-BLK", Decimal("15"), "G")]),
            (20, "POST", "Remove supports, check stem fit", "POST", 2, 8, []),
            (30, "QC", "Fit test on Cherry MX switch", "QC", 0, 5, []),
            (40, "PACK", "Bag with label card", "PACK", 1, 3,
             [("PKG-BAG-SM", Decimal("1"), "EA")]),
        ]),
        ("FG-LAMPSHD-01", "RTG-LAMPSHD", [
            (10, "PRINT", "3D Print Geometric Lampshade", "FDM", 5, 240,
             [("MAT-PLAM-CHAR", Decimal("180"), "G")]),
            (20, "POST", "Sand seam lines, clean interior", "POST", 5, 15, []),
            (30, "QC", "Light diffusion test + visual", "QC", 0, 5, []),
            (40, "PACK", "Wrap in bubble, large box", "PACK", 3, 6,
             [("PKG-BOX-LG", Decimal("1"), "EA"), ("PKG-BUBBLE", Decimal("1"), "EA")]),
        ]),
        ("FG-GEARBOX-01", "RTG-GEARBOX", [
            (10, "PRINT", "Print gears + housing (2 colors)", "FDM", 5, 120,
             [("MAT-PLA-BLU", Decimal("95"), "G"), ("MAT-PLA-WHT", Decimal("45"), "G")]),
            (20, "POST", "Assemble gears into housing", "POST", 3, 12, []),
            (30, "QC", "Function test (gears mesh)", "QC", 0, 5, []),
            (40, "PACK", "Box", "PACK", 1, 3,
             [("PKG-BOX-SM", Decimal("1"), "EA")]),
        ]),
        ("FG-ENCLOSURE-01", "RTG-ENCLOSURE", [
            (10, "PRINT", "Print top + bottom shells", "FDM", 5, 70,
             [("MAT-PETG-BLK", Decimal("55"), "G")]),
            (20, "POST", "Install inserts, test fit", "POST", 3, 8,
             [("CMP-INSERT-M3", Decimal("4"), "EA"), ("CMP-SCREW-M3x8", Decimal("4"), "EA")]),
            (30, "QC", "RPi 5 fit test + port alignment", "QC", 0, 4, []),
            (40, "PACK", "Box with instructions", "PACK", 1, 3,
             [("PKG-BOX-SM", Decimal("1"), "EA")]),
        ]),
        ("FG-TOOLORG-01", "RTG-TOOLORG", [
            (10, "PRINT", "Print organizer base + dividers", "FDM", 5, 140,
             [("MAT-PLA-BLK", Decimal("110"), "G")]),
            (20, "POST", "Install magnets for wall mount", "POST", 3, 10,
             [("CMP-MAGNET-6x3", Decimal("4"), "EA")]),
            (30, "QC", "Magnet strength + visual", "QC", 0, 3, []),
            (40, "PACK", "Box", "PACK", 2, 4,
             [("PKG-BOX-MD", Decimal("1"), "EA")]),
        ]),
        ("FG-PETG-BRACKET", "RTG-BRACKET", [
            (10, "PRINT", "Print PETG bracket (high flow)", "FDM", 5, 50,
             [("MAT-PETGHF-BLK", Decimal("75"), "G")]),
            (20, "POST", "Install M4 inserts, deburr", "POST", 3, 8,
             [("CMP-INSERT-M4", Decimal("4"), "EA")]),
            (30, "QC", "Dimensional check + insert pull test", "QC", 0, 5, []),
            (40, "PACK", "Box", "PACK", 1, 3,
             [("PKG-BOX-SM", Decimal("1"), "EA")]),
        ]),
    ]

    for fg_sku, code, ops in routing_defs:
        routing = Routing(
            product_id=pid(fg_sku),
            code=code,
            name=f"Routing for {products[fg_sku][0].name}",
            is_template=False,
            version=1, revision="1.0",
            is_active=True,
        )
        db.add(routing)
        db.flush()

        total_setup = Decimal("0")
        total_run = Decimal("0")

        for seq, op_code, op_name, wc_key, setup_min, run_min, materials in ops:
            op = RoutingOperation(
                routing_id=routing.id,
                work_center_id=wcs[wc_key].id,
                sequence=seq,
                operation_code=op_code,
                operation_name=op_name,
                setup_time_minutes=Decimal(str(setup_min)),
                run_time_minutes=Decimal(str(run_min)),
                runtime_source="manual",
                is_active=True,
            )
            db.add(op)
            db.flush()

            total_setup += Decimal(str(setup_min))
            total_run += Decimal(str(run_min))

            # Attach materials to this operation
            for comp_sku, qty, unit in materials:
                db.add(RoutingOperationMaterial(
                    routing_operation_id=op.id,
                    component_id=pid(comp_sku),
                    quantity=qty,
                    quantity_per="unit",
                    unit=unit,
                ))

        routing.total_setup_time_minutes = total_setup
        routing.total_run_time_minutes = total_run
        routings[fg_sku] = routing

    db.flush()
    print(f"  Routings: {len(routings)} created (each with PRINT > POST > QC > PACK operations)")
    return routings


def seed_inventory(db: Session, products, location_id=1):
    """Set on-hand inventory for all products."""
    from app.models.inventory import Inventory, InventoryTransaction

    count = 0
    for sku, (product, stock_qty) in products.items():
        if stock_qty <= 0:
            continue

        inv = Inventory(
            product_id=product.id,
            location_id=location_id,
            on_hand_quantity=Decimal(str(stock_qty)),
            allocated_quantity=Decimal("0"),
            last_counted=days_ago(3),
        )
        db.add(inv)

        # Create a receipt transaction as audit trail
        unit = product.unit or "EA"
        cost_per = product.standard_cost or product.average_cost or Decimal("0")
        db.add(InventoryTransaction(
            product_id=product.id,
            location_id=location_id,
            transaction_type="receipt",
            reference_type="adjustment",
            quantity=Decimal(str(stock_qty)),
            unit=unit,
            cost_per_unit=cost_per,
            total_cost=cost_per * Decimal(str(stock_qty)),
            notes="Initial inventory seed",
            transaction_date=date_ago(30),
            created_at=days_ago(30),
            created_by="seed_script",
        ))
        count += 1

    db.flush()
    print(f"  Inventory: {count} products stocked with receipt transactions")


def seed_sales_orders(db: Session, products, customers, admin_user):
    """Realistic sales orders at various stages."""
    from app.models.sales_order import SalesOrder, SalesOrderLine

    orders = []

    so_data = [
        # (order_num, customer_idx, status, payment_status, days_ago, lines, notes)
        ("SO-2026-0041", 0, "completed", "paid", 25, [
            ("FG-WALLMOUNT-01", 10, None),
            ("FG-CABLEORG-01", 20, None),
        ], "Monthly standing order for MakerSpace PDX."),
        ("SO-2026-0042", 1, "completed", "paid", 20, [
            ("FG-ENCLOSURE-01", 50, None),
        ], "Bulk RPi enclosure order for Rapid Proto Labs."),
        ("SO-2026-0043", 2, "in_production", "paid", 12, [
            ("FG-PLANTER-01", 30, None),
            ("FG-LAMPSHD-01", 15, None),
        ], "Large order from PrintFarm Co. In production."),
        ("SO-2026-0044", 3, "confirmed", "paid", 8, [
            ("FG-GEARBOX-01", 5, None),
            ("FG-KEYCAP-SET", 10, None),
            ("FG-PHONESTD-01", 15, None),
        ], "DesignWorks multi-product order. Ready for production."),
        ("SO-2026-0045", 4, "draft", "pending", 3, [
            ("FG-TOOLORG-01", 8, None),
            ("FG-PETG-BRACKET", 20, None),
        ], "EduPrint Academy PO pending approval."),
        ("SO-2026-0046", 0, "shipped", "paid", 18, [
            ("FG-WALLMOUNT-01", 5, "1Z999AA10123456784"),
            ("FG-PHONESTD-01", 5, "1Z999AA10123456784"),
        ], "Shipped to MakerSpace PDX."),
        ("SO-2026-0047", 1, "ready_to_ship", "paid", 10, [
            ("FG-PETG-BRACKET", 25, None),
        ], "Completed production, awaiting pickup."),
    ]

    for order_num, cust_idx, status, pay_status, ago, lines, notes in so_data:
        cust = customers[cust_idx]

        # Calculate totals from lines
        line_total = Decimal("0")
        for fg_sku, qty, _ in lines:
            price = products[fg_sku][0].selling_price or Decimal("0")
            line_total += price * qty

        tax = line_total * Decimal("0.0825")  # 8.25% tax
        grand = line_total + tax

        so = SalesOrder(
            order_number=order_num,
            user_id=admin_user.id,
            customer_id=None,  # FK is to users.id; seed customers don't have user accounts
            customer_name=f"{cust.first_name} {cust.last_name}",
            customer_email=cust.email,
            customer_phone=cust.phone,
            product_name=products[lines[0][0]][0].name,
            product_id=products[lines[0][0]][0].id,
            quantity=lines[0][1],
            material_type="PLA",
            order_type="line_item",
            source="manual",
            status=status,
            payment_status=pay_status,
            unit_price=products[lines[0][0]][0].selling_price or Decimal("0"),
            total_price=line_total,
            tax_amount=tax,
            tax_rate=Decimal("0.0825"),
            is_taxable=True,
            grand_total=grand,
            internal_notes=notes,
            shipping_address_line1=cust.billing_address_line1,
            shipping_city=cust.billing_city,
            shipping_state=cust.billing_state,
            shipping_zip=cust.billing_zip,
            shipping_country=cust.billing_country or "US",
            created_at=days_ago(ago),
            confirmed_at=days_ago(ago - 1) if status != "draft" else None,
        )

        if status == "shipped":
            so.tracking_number = lines[0][2] if lines[0][2] else None
            so.carrier = "UPS"
            so.shipped_at = days_ago(ago - 5)
            so.fulfillment_status = "shipped"

        if status == "ready_to_ship":
            so.fulfillment_status = "ready"

        if status == "completed":
            so.actual_completion_date = days_ago(ago - 7)

        db.add(so)
        db.flush()

        # Add line items
        for i, (fg_sku, qty, _tracking) in enumerate(lines):
            fg = products[fg_sku][0]
            unit_price = fg.selling_price or Decimal("0")
            db.add(SalesOrderLine(
                sales_order_id=so.id,
                product_id=fg.id,
                quantity=Decimal(str(qty)),
                unit_price=unit_price,
                total=unit_price * qty,
                tax_rate=Decimal("0.0825"),
                created_by=admin_user.id,
            ))

        orders.append(so)

    db.flush()
    print(f"  Sales Orders: {len(orders)} created (draft > shipped lifecycle)")
    return orders


def seed_production_orders(db: Session, products, boms, routings, wcs, sales_orders):
    """Production orders with operations copied from routings."""
    from app.models.production_order import (
        ProductionOrder, ProductionOrderOperation, ProductionOrderOperationMaterial
    )
    from app.models.manufacturing import RoutingOperation, RoutingOperationMaterial

    pos = []

    po_data = [
        # (code, fg_sku, qty, status, source, so_idx, priority, days_ago)
        ("WO-2026-0031", "FG-WALLMOUNT-01", 15, "completed", "sales_order", 0, 3, 24),
        ("WO-2026-0032", "FG-CABLEORG-01", 25, "completed", "sales_order", 0, 3, 24),
        ("WO-2026-0033", "FG-ENCLOSURE-01", 50, "completed", "sales_order", 1, 2, 19),
        ("WO-2026-0034", "FG-PLANTER-01", 30, "in_progress", "sales_order", 2, 2, 11),
        ("WO-2026-0035", "FG-LAMPSHD-01", 15, "in_progress", "sales_order", 2, 2, 11),
        ("WO-2026-0036", "FG-GEARBOX-01", 5, "released", "sales_order", 3, 3, 7),
        ("WO-2026-0037", "FG-KEYCAP-SET", 10, "released", "sales_order", 3, 3, 7),
        ("WO-2026-0038", "FG-PHONESTD-01", 15, "released", "sales_order", 3, 3, 7),
        ("WO-2026-0039", "FG-WALLMOUNT-01", 20, "draft", "mrp_planned", None, 4, 2),
        ("WO-2026-0040", "FG-PETG-BRACKET", 25, "completed", "sales_order", 6, 2, 14),
    ]

    for code, fg_sku, qty, status, source, so_idx, priority, ago in po_data:
        fg = products[fg_sku][0]
        bom = boms.get(fg_sku)
        routing = routings.get(fg_sku)

        po = ProductionOrder(
            code=code,
            product_id=fg.id,
            bom_id=bom.id if bom else None,
            routing_id=routing.id if routing else None,
            sales_order_id=sales_orders[so_idx].id if so_idx is not None else None,
            quantity_ordered=Decimal(str(qty)),
            status=status,
            source=source,
            order_type="MAKE_TO_ORDER" if so_idx is not None else "MAKE_TO_STOCK",
            priority=priority,
            due_date=date_ago(ago - 10),
            scheduled_start=days_ago(ago),
            created_at=days_ago(ago),
        )

        if status == "completed":
            po.quantity_completed = Decimal(str(qty))
            po.actual_start = days_ago(ago)
            po.actual_end = days_ago(ago - 5)
            po.completed_at = days_ago(ago - 5)

        if status == "in_progress":
            po.quantity_completed = Decimal(str(int(qty * 0.4)))  # 40% done
            po.actual_start = days_ago(ago)

        db.add(po)
        db.flush()

        # Copy routing operations → production order operations
        if routing:
            rtg_ops = (
                db.query(RoutingOperation)
                .filter(RoutingOperation.routing_id == routing.id)
                .order_by(RoutingOperation.sequence)
                .all()
            )

            for rtg_op in rtg_ops:
                # Determine operation status based on PO status
                if status == "completed":
                    op_status = "complete"
                elif status == "in_progress":
                    if rtg_op.sequence <= 10:
                        op_status = "running" if rtg_op.operation_code == "PRINT" else "complete"
                    elif rtg_op.sequence == 20:
                        op_status = "running"
                    else:
                        op_status = "pending"
                elif status == "released":
                    op_status = "pending"
                else:
                    op_status = "pending"

                poo = ProductionOrderOperation(
                    production_order_id=po.id,
                    routing_operation_id=rtg_op.id,
                    work_center_id=rtg_op.work_center_id,
                    sequence=rtg_op.sequence,
                    operation_code=rtg_op.operation_code,
                    operation_name=rtg_op.operation_name,
                    status=op_status,
                    planned_setup_minutes=rtg_op.setup_time_minutes,
                    planned_run_minutes=rtg_op.run_time_minutes * qty,
                )

                if op_status == "complete":
                    poo.actual_setup_minutes = rtg_op.setup_time_minutes
                    poo.actual_run_minutes = rtg_op.run_time_minutes * qty * Decimal("1.05")
                    poo.actual_start = days_ago(ago)
                    poo.actual_end = days_ago(ago - 2)
                    poo.quantity_completed = Decimal(str(qty))

                if op_status == "running":
                    poo.actual_start = days_ago(3)

                db.add(poo)
                db.flush()

                # Copy operation materials
                rtg_mats = (
                    db.query(RoutingOperationMaterial)
                    .filter(RoutingOperationMaterial.routing_operation_id == rtg_op.id)
                    .all()
                )
                for rm in rtg_mats:
                    mat_status = "consumed" if op_status == "complete" else "pending"
                    if op_status == "running":
                        mat_status = "allocated"

                    poom = ProductionOrderOperationMaterial(
                        production_order_operation_id=poo.id,
                        component_id=rm.component_id,
                        routing_operation_material_id=rm.id,
                        quantity_required=rm.quantity * qty,
                        unit=rm.unit,
                        status=mat_status,
                    )
                    if mat_status == "consumed":
                        poom.quantity_consumed = rm.quantity * qty
                        poom.consumed_at = days_ago(ago - 3)
                    elif mat_status == "allocated":
                        poom.quantity_allocated = rm.quantity * qty

                    db.add(poom)

        pos.append(po)

    db.flush()
    print(f"  Production Orders: {len(pos)} created with operations + materials")
    return pos


def seed_purchase_orders(db: Session, products, vendors):
    """Purchase history showing received and pending orders."""
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine

    po_data = [
        # (po_num, vendor_idx, status, days_ago, lines: [(sku, qty_ordered, qty_received, unit_cost)])
        ("PO-2026-0021", 0, "received", 45, [
            ("MAT-PLA-BLK", Decimal("10"), Decimal("10"), Decimal("20.00")),
            ("MAT-PLA-WHT", Decimal("5"), Decimal("5"), Decimal("20.00")),
            ("MAT-PETG-BLK", Decimal("5"), Decimal("5"), Decimal("24.00")),
        ]),
        ("PO-2026-0022", 1, "received", 30, [
            ("MAT-PLAM-BLK", Decimal("8"), Decimal("8"), Decimal("22.00")),
            ("MAT-PLAM-WHT", Decimal("4"), Decimal("4"), Decimal("22.00")),
            ("MAT-PLAM-CHAR", Decimal("4"), Decimal("4"), Decimal("22.00")),
        ]),
        ("PO-2026-0023", 3, "received", 20, [
            ("PKG-BOX-SM", Decimal("200"), Decimal("200"), Decimal("0.75")),
            ("PKG-BOX-MD", Decimal("100"), Decimal("100"), Decimal("1.10")),
            ("PKG-BOX-LG", Decimal("50"), Decimal("50"), Decimal("1.65")),
            ("PKG-BAG-SM", Decimal("500"), Decimal("500"), Decimal("0.04")),
        ]),
        ("PO-2026-0024", 4, "received", 15, [
            ("CMP-INSERT-M3", Decimal("500"), Decimal("500"), Decimal("0.12")),
            ("CMP-INSERT-M4", Decimal("300"), Decimal("300"), Decimal("0.18")),
            ("CMP-SCREW-M3x8", Decimal("1000"), Decimal("1000"), Decimal("0.05")),
            ("CMP-SCREW-M3x12", Decimal("500"), Decimal("500"), Decimal("0.06")),
            ("CMP-MAGNET-6x3", Decimal("200"), Decimal("200"), Decimal("0.35")),
        ]),
        ("PO-2026-0025", 0, "ordered", 5, [
            ("MAT-PLA-BLK", Decimal("10"), Decimal("0"), Decimal("20.00")),
            ("MAT-PLA-RED", Decimal("5"), Decimal("0"), Decimal("20.00")),
            ("MAT-PLA-BLU", Decimal("5"), Decimal("0"), Decimal("20.00")),
            ("MAT-PETGHF-BLK", Decimal("5"), Decimal("0"), Decimal("24.00")),
        ]),
        ("PO-2026-0026", 2, "ordered", 3, [
            ("MAT-PLACF-BLK", Decimal("3"), Decimal("0"), Decimal("45.00")),
            ("MAT-TPU-BLK", Decimal("3"), Decimal("0"), Decimal("35.00")),
        ]),
    ]

    count = 0
    for po_num, vendor_idx, status, ago, lines in po_data:
        subtotal = sum(q_ord * uc for _, q_ord, _, uc in lines)
        shipping = Decimal("12.00") if subtotal < Decimal("100") else Decimal("0")

        po = PurchaseOrder(
            po_number=po_num,
            vendor_id=vendors[vendor_idx].id,
            status=status,
            order_date=date_ago(ago),
            expected_date=date_ago(ago - 7),
            subtotal=subtotal,
            shipping_cost=shipping,
            total_amount=subtotal + shipping,
            created_by="1",
            created_at=days_ago(ago),
        )

        if status == "received":
            po.received_date = date_ago(ago - 5)

        db.add(po)
        db.flush()

        for i, (sku, qty_ord, qty_recv, uc) in enumerate(lines):
            db.add(PurchaseOrderLine(
                purchase_order_id=po.id,
                product_id=products[sku][0].id,
                line_number=i + 1,
                quantity_ordered=qty_ord,
                quantity_received=qty_recv,
                purchase_unit="KG" if sku.startswith("MAT-") else "EA",
                unit_cost=uc,
                line_total=qty_ord * uc,
            ))

        count += 1

    db.flush()
    print(f"  Purchase Orders: {count} created (received + in-transit)")


def seed_scrap_and_adjustment_reasons(db: Session):
    """Scrap reasons and adjustment reasons for dropdowns."""
    from app.models.scrap_reason import ScrapReason
    from app.models.adjustment_reason import AdjustmentReason

    scrap_reasons = [
        ("adhesion", "Bed Adhesion Failure"),
        ("layer_shift", "Layer Shift"),
        ("stringing", "Excessive Stringing"),
        ("warping", "Warping"),
        ("nozzle_clog", "Nozzle Clog"),
        ("spaghetti", "Spaghetti / Detach"),
        ("wrong_color", "Wrong Color Loaded"),
        ("other", "Other"),
    ]
    for code, name in scrap_reasons:
        db.add(ScrapReason(code=code, name=name, active=True))

    adj_reasons = [
        ("cycle_count", "Cycle Count Adjustment"),
        ("damage", "Damaged Goods"),
        ("sample", "Sample / Giveaway"),
        ("rework", "Reworked / Returned to Stock"),
        ("initial_load", "Initial Inventory Load"),
        ("other", "Other"),
    ]
    for code, name in adj_reasons:
        db.add(AdjustmentReason(code=code, name=name, active=True))

    db.flush()
    print(f"  Scrap Reasons: {len(scrap_reasons)} | Adjustment Reasons: {len(adj_reasons)}")


def seed_company_settings(db: Session):
    """Company settings for the dev environment."""
    from app.models.company_settings import CompanySettings

    settings = CompanySettings(
        company_name="BLB 3D",
        timezone="America/New_York",
    )
    db.add(settings)
    db.flush()
    print("  Company Settings: BLB 3D")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Seed dev database with realistic data")
    parser.add_argument("--reset", action="store_true", help="Truncate all data before seeding")
    args = parser.parse_args()

    print("=" * 65)
    print("  FilaOps Dev Data Seeder")
    print("=" * 65)

    verify_database()

    db: Session = SessionLocal()

    try:
        if args.reset:
            confirm = input("\n  This will DELETE ALL DATA in 'filaops'. Type 'yes' to confirm: ")
            if confirm.strip().lower() != "yes":
                print("  Aborted.")
                return
            reset_database(db)

        print("\n-- Seeding -----------------------------------------------------")
        seed_gl_accounts(db)
        seed_uoms(db)
        seed_company_settings(db)
        seed_scrap_and_adjustment_reasons(db)
        locs = seed_locations(db)
        admin = seed_admin_user(db)
        customers = seed_customers(db)
        vendors = seed_vendors(db)
        categories = seed_categories(db)
        mt_objs, color_objs = seed_materials_and_colors(db)
        products = seed_products(db, categories, mt_objs, color_objs, vendors)
        wcs = seed_work_centers_and_resources(db)
        boms = seed_boms(db, products)
        routings = seed_routings(db, products, boms, wcs)
        seed_inventory(db, products, location_id=locs["warehouse"])
        sales_orders = seed_sales_orders(db, products, customers, admin)
        seed_production_orders(db, products, boms, routings, wcs, sales_orders)
        seed_purchase_orders(db, products, vendors)

        db.commit()

        print("\n-- Summary -----------------------------------------------------")
        print("  Login:  admin@filaops.dev / FilaOps2026!")
        print("  Data includes:")
        print("    -14 raw materials (filament with G/KG UOM)")
        print("    -11 components & packaging (EA)")
        print("    -10 finished goods with BOMs + routings")
        print("    -5 customers with real addresses")
        print("    -5 vendors (Bambu Lab, Polymaker, etc.)")
        print("    -7 sales orders (draft > shipped)")
        print("    -10 production orders with operations")
        print("    -6 purchase orders (received + pending)")
        print("    -Inventory levels + receipt transactions")
        print("    -Reorder points configured for MRP")
        print("=" * 65)

    except Exception as e:
        db.rollback()
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
