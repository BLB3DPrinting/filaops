"""
Seed Example Data for FilaOps

This script seeds the database with:
1. Example items for each category (one per category)
2. Comprehensive materials list (material types + colors)

Run with: python -m backend.scripts.seed_example_data
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.db.session import SessionLocal
from app.models.item_category import ItemCategory
from app.models.product import Product
from app.models.material import MaterialType, Color, MaterialColor


def get_or_create_category(db: Session, code: str, name: str, parent_code: Optional[str] = None, sort_order: int = 0) -> ItemCategory:
    """Get existing category or create if it doesn't exist"""
    category = db.query(ItemCategory).filter(ItemCategory.code == code).first()
    if not category:
        parent = None
        if parent_code:
            parent = db.query(ItemCategory).filter(ItemCategory.code == parent_code).first()
        
        category = ItemCategory(
            code=code,
            name=name,
            parent_id=parent.id if parent else None,
            sort_order=sort_order,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(category)
        db.flush()
        db.refresh(category)
    return category


def ensure_categories_exist(db: Session):
    """Ensure all required categories exist, create them if missing"""
    print("\n📁 Ensuring categories exist...")
    
    categories_to_create = [
        # Root categories
        {"code": "FILAMENT", "name": "Filament", "parent_code": None, "sort_order": 1},
        {"code": "PACKAGING", "name": "Packaging", "parent_code": None, "sort_order": 2},
        {"code": "HARDWARE", "name": "Hardware", "parent_code": None, "sort_order": 3},
        {"code": "FINISHED_GOODS", "name": "Finished Goods", "parent_code": None, "sort_order": 4},
        {"code": "SERVICES", "name": "Services", "parent_code": None, "sort_order": 5},
        # Filament subcategories
        {"code": "PLA", "name": "PLA", "parent_code": "FILAMENT", "sort_order": 1},
        {"code": "PETG", "name": "PETG", "parent_code": "FILAMENT", "sort_order": 2},
        {"code": "ABS", "name": "ABS", "parent_code": "FILAMENT", "sort_order": 3},
        {"code": "TPU", "name": "TPU", "parent_code": "FILAMENT", "sort_order": 4},
        # Packaging subcategories
        {"code": "BOXES", "name": "Boxes", "parent_code": "PACKAGING", "sort_order": 1},
        {"code": "BAGS", "name": "Bags", "parent_code": "PACKAGING", "sort_order": 2},
        # Hardware subcategories
        {"code": "FASTENERS", "name": "Fasteners", "parent_code": "HARDWARE", "sort_order": 1},
        {"code": "INSERTS", "name": "Heat Set Inserts", "parent_code": "HARDWARE", "sort_order": 2},
        # Finished goods subcategories
        {"code": "STANDARD_PRODUCTS", "name": "Standard Products", "parent_code": "FINISHED_GOODS", "sort_order": 1},
        {"code": "CUSTOM_PRODUCTS", "name": "Custom Products", "parent_code": "FINISHED_GOODS", "sort_order": 2},
    ]
    
    # First pass: Create root categories
    for cat_data in categories_to_create:
        if cat_data["parent_code"] is None:
            category = db.query(ItemCategory).filter(ItemCategory.code == cat_data["code"]).first()
            if not category:
                category = ItemCategory(
                    code=cat_data["code"],
                    name=cat_data["name"],
                    parent_id=None,
                    sort_order=cat_data["sort_order"],
                    is_active=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(category)
                print(f"  ✅ Created category: {cat_data['code']}")

    db.flush()

    # Second pass: Create child categories
    for cat_data in categories_to_create:
        if cat_data["parent_code"] is not None:
            category = db.query(ItemCategory).filter(ItemCategory.code == cat_data["code"]).first()
            if not category:
                parent = db.query(ItemCategory).filter(ItemCategory.code == cat_data["parent_code"]).first()
                if parent:
                    category = ItemCategory(
                        code=cat_data["code"],
                        name=cat_data["name"],
                        parent_id=parent.id,
                        sort_order=cat_data["sort_order"],
                        is_active=True,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(category)
                    print(f"  ✅ Created category: {cat_data['code']} (under {cat_data['parent_code']})")
                else:
                    print(f"  ⚠️  Parent category {cat_data['parent_code']} not found for {cat_data['code']}")

    db.flush()


def seed_example_items(db: Session):
    """Seed one example item per category"""
    print("\n📦 Seeding example items by category...")
    
    # Ensure categories exist first
    ensure_categories_exist(db)
    
    examples = [
        # Finished goods examples - one for each major material category
        {
            "sku": "SEED-EXAMPLE-PLA-001",
            "name": "Example Standard Product (PLA)",
            "description": "Example finished good product - can be made from any material (seeded example data)",
            "category_code": "STANDARD_PRODUCTS",
            "item_type": "finished_good",
            "procurement_type": "make",
            "standard_cost": Decimal("5.00"),
            "selling_price": Decimal("15.00"),
        },
        {
            "sku": "SEED-EXAMPLE-PETG-001",
            "name": "Example Custom Product (PETG)",
            "description": "Example custom finished good product - can be made from any material (seeded example data)",
            "category_code": "CUSTOM_PRODUCTS",
            "item_type": "finished_good",
            "procurement_type": "make",
            "standard_cost": Decimal("6.00"),
            "selling_price": Decimal("18.00"),
        },
        {
            "sku": "SEED-EXAMPLE-ABS-001",
            "name": "Example Durable Product (ABS)",
            "description": "Example finished good product requiring durable material (seeded example data)",
            "category_code": "STANDARD_PRODUCTS",
            "item_type": "finished_good",
            "procurement_type": "make",
            "standard_cost": Decimal("7.00"),
            "selling_price": Decimal("20.00"),
        },
        {
            "sku": "SEED-EXAMPLE-TPU-001",
            "name": "Example Flexible Product (TPU)",
            "description": "Example flexible finished good product (seeded example data)",
            "category_code": "CUSTOM_PRODUCTS",
            "item_type": "finished_good",
            "procurement_type": "make",
            "standard_cost": Decimal("8.00"),
            "selling_price": Decimal("22.00"),
        },
        
        # Packaging examples
        {
            "sku": "SEED-EXAMPLE-BOX-001",
            "name": "Example Shipping Box",
            "description": "Standard shipping box for products (seeded example data)",
            "category_code": "BOXES",
            "item_type": "supply",
            "procurement_type": "buy",
            "standard_cost": Decimal("0.50"),
            "selling_price": None,
        },
        {
            "sku": "SEED-EXAMPLE-BAG-001",
            "name": "Example Poly Bag",
            "description": "Poly bag for product packaging (seeded example data)",
            "category_code": "BAGS",
            "item_type": "supply",
            "procurement_type": "buy",
            "standard_cost": Decimal("0.10"),
            "selling_price": None,
        },
        
        # Hardware examples
        {
            "sku": "SEED-EXAMPLE-FAST-001",
            "name": "Example Fastener Set",
            "description": "Example hardware fastener (seeded example data)",
            "category_code": "FASTENERS",
            "item_type": "component",
            "procurement_type": "buy",
            "standard_cost": Decimal("0.25"),
            "selling_price": None,
        },
        {
            "sku": "SEED-EXAMPLE-INSERT-001",
            "name": "Example Heat Set Insert",
            "description": "M3 heat set insert for 3D printed parts (seeded example data)",
            "category_code": "INSERTS",
            "item_type": "component",
            "procurement_type": "buy",
            "standard_cost": Decimal("0.15"),
            "selling_price": None,
        },
        
        # Finished goods examples
        {
            "sku": "SEED-EXAMPLE-STD-001",
            "name": "Example Standard Product",
            "description": "Example standard finished product (seeded example data)",
            "category_code": "STANDARD_PRODUCTS",
            "item_type": "finished_good",
            "procurement_type": "make",
            "standard_cost": Decimal("10.00"),
            "selling_price": Decimal("25.00"),
        },
        {
            "sku": "SEED-EXAMPLE-CUST-001",
            "name": "Example Custom Product",
            "description": "Example custom finished product (seeded example data)",
            "category_code": "CUSTOM_PRODUCTS",
            "item_type": "finished_good",
            "procurement_type": "make",
            "standard_cost": Decimal("12.00"),
            "selling_price": Decimal("30.00"),
        },
    ]
    
    created = 0
    skipped = 0
    
    for example in examples:
        # Check if SKU already exists
        existing = db.query(Product).filter(Product.sku == example["sku"]).first()
        if existing:
            print(f"  ⏭️  Skipped {example['sku']} (already exists)")
            skipped += 1
            continue
        
        # Get category (should exist after ensure_categories_exist)
        category = db.query(ItemCategory).filter(ItemCategory.code == example["category_code"]).first()
        if not category:
            print(f"  ❌ ERROR: Category {example['category_code']} not found after ensuring categories exist!")
            print(f"     This should not happen. Skipping {example['sku']}")
            skipped += 1
            continue
        
        # Create product
        product = Product(
            sku=example["sku"],
            name=example["name"],
            description=example["description"],
            category_id=category.id,
            item_type=example["item_type"],
            procurement_type=example["procurement_type"],
            standard_cost=example["standard_cost"],
            selling_price=example["selling_price"],
            unit="EA",
            active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(product)
        created += 1
        print(f"  ✅ Created {example['sku']}: {example['name']}")
    
    db.flush()
    print(f"\n  📊 Created {created} example items, skipped {skipped}")
    return created, skipped


def seed_materials(db: Session):
    """Seed basic materials list (material types only, no colors/products)"""
    print("\n🎨 Seeding basic material types (colors and products should be imported via CSV)...")
    
    # Basic BambuLab material types - just the types, no colors
    # Users should import their full material+color list via CSV
    material_types = [
        # PLA variants
        {
            "code": "PLA_BASIC",
            "name": "PLA Basic",
            "base_material": "PLA",
            "density": Decimal("1.24"),
            "base_price_per_kg": Decimal("20.00"),
            "price_multiplier": Decimal("1.0"),
            "description": "Standard PLA filament, easy to print, good for most applications",
            "strength_rating": 5,
        },
        {
            "code": "PLA_MATTE",
            "name": "PLA Matte",
            "base_material": "PLA",
            "density": Decimal("1.24"),
            "base_price_per_kg": Decimal("22.00"),
            "price_multiplier": Decimal("1.1"),
            "description": "Matte finish PLA, same strength as basic PLA with non-glossy surface",
            "strength_rating": 5,
        },
        {
            "code": "PLA_SILK",
            "name": "PLA Silk",
            "base_material": "PLA",
            "density": Decimal("1.24"),
            "base_price_per_kg": Decimal("25.00"),
            "price_multiplier": Decimal("1.25"),
            "description": "Silk finish PLA with glossy, smooth surface",
            "strength_rating": 5,
        },
        {
            "code": "PLA_SILK_MULTI",
            "name": "PLA Silk Multi-Color",
            "base_material": "PLA",
            "density": Decimal("1.24"),
            "base_price_per_kg": Decimal("28.00"),
            "price_multiplier": Decimal("1.4"),
            "description": "Multi-color silk PLA with gradient effects",
            "strength_rating": 5,
        },
        {
            "code": "PLA_CF",
            "name": "PLA-CF",
            "base_material": "PLA",
            "density": Decimal("1.30"),
            "base_price_per_kg": Decimal("45.00"),
            "price_multiplier": Decimal("2.25"),
            "description": "Carbon fiber reinforced PLA, requires hardened nozzle",
            "strength_rating": 9,
        },
        {
            "code": "PLA_METALLIC",
            "name": "PLA Metallic",
            "base_material": "PLA",
            "density": Decimal("1.24"),
            "base_price_per_kg": Decimal("26.00"),
            "price_multiplier": Decimal("1.3"),
            "description": "Metallic finish PLA with metallic appearance",
            "strength_rating": 5,
        },
        
        # PETG variants
        {
            "code": "PETG_BASIC",
            "name": "PETG Basic",
            "base_material": "PETG",
            "density": Decimal("1.27"),
            "base_price_per_kg": Decimal("24.00"),
            "price_multiplier": Decimal("1.2"),
            "description": "Standard PETG filament, stronger than PLA, good layer adhesion",
            "strength_rating": 7,
        },
        {
            "code": "PETG_HF",
            "name": "PETG High Flow",
            "base_material": "PETG",
            "density": Decimal("1.27"),
            "base_price_per_kg": Decimal("24.00"),
            "price_multiplier": Decimal("1.2"),
            "description": "High-flow PETG, optimized for faster printing",
            "strength_rating": 7,
        },
        {
            "code": "PETG_CF",
            "name": "PETG-CF",
            "base_material": "PETG",
            "density": Decimal("1.35"),
            "base_price_per_kg": Decimal("48.00"),
            "price_multiplier": Decimal("2.4"),
            "description": "Carbon fiber reinforced PETG, requires hardened nozzle",
            "strength_rating": 9,
        },
        {
            "code": "PETG_TRANS",
            "name": "PETG Translucent",
            "base_material": "PETG",
            "density": Decimal("1.27"),
            "base_price_per_kg": Decimal("24.00"),
            "price_multiplier": Decimal("1.2"),
            "description": "Translucent PETG, clear finish with good light transmission",
            "strength_rating": 7,
        },
        
        # ABS variants
        {
            "code": "ABS_BASIC",
            "name": "ABS Basic",
            "base_material": "ABS",
            "density": Decimal("1.04"),
            "base_price_per_kg": Decimal("22.00"),
            "price_multiplier": Decimal("1.1"),
            "requires_enclosure": True,
            "description": "ABS filament, requires heated enclosure, strong and durable",
            "strength_rating": 8,
        },
        {
            "code": "ABS_GF",
            "name": "ABS-GF",
            "base_material": "ABS",
            "density": Decimal("1.10"),
            "base_price_per_kg": Decimal("35.00"),
            "price_multiplier": Decimal("1.75"),
            "requires_enclosure": True,
            "description": "Glass fiber reinforced ABS, very strong and rigid",
            "strength_rating": 9,
        },
        
        # ASA variants
        {
            "code": "ASA_BASIC",
            "name": "ASA Basic",
            "base_material": "ASA",
            "density": Decimal("1.07"),
            "base_price_per_kg": Decimal("28.00"),
            "price_multiplier": Decimal("1.4"),
            "requires_enclosure": True,
            "description": "ASA filament, UV resistant, good for outdoor applications",
            "strength_rating": 8,
        },
        {
            "code": "ASA_CF",
            "name": "ASA-CF",
            "base_material": "ASA",
            "density": Decimal("1.12"),
            "base_price_per_kg": Decimal("50.00"),
            "price_multiplier": Decimal("2.5"),
            "requires_enclosure": True,
            "description": "Carbon fiber reinforced ASA, UV resistant and very strong",
            "strength_rating": 10,
        },
        
        # TPU variants
        {
            "code": "TPU_95A",
            "name": "TPU 95A",
            "base_material": "TPU",
            "density": Decimal("1.20"),
            "base_price_per_kg": Decimal("35.00"),
            "price_multiplier": Decimal("1.75"),
            "description": "Flexible TPU 95A, soft and elastic",
            "strength_rating": 4,
        },
        {
            "code": "TPU_68D",
            "name": "TPU 68D",
            "base_material": "TPU",
            "density": Decimal("1.20"),
            "base_price_per_kg": Decimal("38.00"),
            "price_multiplier": Decimal("1.9"),
            "description": "Rigid TPU 68D, more rigid than 95A but still flexible",
            "strength_rating": 6,
        },
        
        # Specialty materials
        {
            "code": "PAHT_CF",
            "name": "PAHT-CF",
            "base_material": "PAHT",
            "density": Decimal("1.15"),
            "base_price_per_kg": Decimal("55.00"),
            "price_multiplier": Decimal("2.75"),
            "requires_enclosure": True,
            "description": "High-temperature nylon with carbon fiber, very strong",
            "strength_rating": 10,
        },
        {
            "code": "PC",
            "name": "PC (Polycarbonate)",
            "base_material": "PC",
            "density": Decimal("1.20"),
            "base_price_per_kg": Decimal("40.00"),
            "price_multiplier": Decimal("2.0"),
            "requires_enclosure": True,
            "description": "Polycarbonate, high strength and temperature resistance",
            "strength_rating": 9,
        },
    ]
    
    # NOTE: Colors and material+color combinations are NOT seeded here.
    # Users should import their material inventory via CSV using the material import endpoint.
    # This seed function only creates the basic material type definitions.
    
    # Create material types
    material_type_objs = {}
    created_types = 0
    
    for mt_data in material_types:
        existing = db.query(MaterialType).filter(MaterialType.code == mt_data["code"]).first()
        if existing:
            print(f"  ⏭️  Material type {mt_data['code']} already exists")
            material_type_objs[mt_data["code"]] = existing
            continue
        
        mt = MaterialType(
            code=mt_data["code"],
            name=mt_data["name"],
            base_material=mt_data["base_material"],
            density=mt_data["density"],
            base_price_per_kg=mt_data["base_price_per_kg"],
            price_multiplier=mt_data.get("price_multiplier", Decimal("1.0")),
            description=mt_data.get("description"),
            strength_rating=mt_data.get("strength_rating"),
            requires_enclosure=mt_data.get("requires_enclosure", False),
            active=True,
            is_customer_visible=True,
            display_order=mt_data.get("display_order", 100),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(mt)
        db.flush()
        material_type_objs[mt_data["code"]] = mt
        created_types += 1
        print(f"  ✅ Created material type: {mt_data['name']}")

    db.flush()

    # Seed basic colors so users can create materials without CSV import
    basic_colors = [
        {"code": "BLK", "name": "Black", "hex_code": "#000000", "display_order": 1},
        {"code": "WHT", "name": "White", "hex_code": "#FFFFFF", "display_order": 2},
        {"code": "GRY", "name": "Gray", "hex_code": "#808080", "display_order": 3},
        {"code": "RED", "name": "Red", "hex_code": "#FF0000", "display_order": 4},
        {"code": "BLU", "name": "Blue", "hex_code": "#0000FF", "display_order": 5},
        {"code": "GRN", "name": "Green", "hex_code": "#00FF00", "display_order": 6},
        {"code": "YLW", "name": "Yellow", "hex_code": "#FFFF00", "display_order": 7},
        {"code": "ORG", "name": "Orange", "hex_code": "#FFA500", "display_order": 8},
        {"code": "PRP", "name": "Purple", "hex_code": "#800080", "display_order": 9},
        {"code": "PNK", "name": "Pink", "hex_code": "#FFC0CB", "display_order": 10},
        {"code": "BRN", "name": "Brown", "hex_code": "#8B4513", "display_order": 11},
        {"code": "TAN", "name": "Tan/Beige", "hex_code": "#D2B48C", "display_order": 12},
        {"code": "GLD", "name": "Gold", "hex_code": "#FFD700", "display_order": 13},
        {"code": "SLV", "name": "Silver", "hex_code": "#C0C0C0", "display_order": 14},
        {"code": "CLR", "name": "Clear/Transparent", "hex_code": "#FFFFFF", "display_order": 15},
    ]

    color_objs = {}
    created_colors = 0

    for color_data in basic_colors:
        existing = db.query(Color).filter(Color.code == color_data["code"]).first()
        if existing:
            color_objs[color_data["code"]] = existing
            continue

        color = Color(
            code=color_data["code"],
            name=color_data["name"],
            hex_code=color_data["hex_code"],
            display_order=color_data["display_order"],
            active=True,
            is_customer_visible=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(color)
        db.flush()
        color_objs[color_data["code"]] = color
        created_colors += 1
        print(f"  ✅ Created color: {color_data['name']}")

    db.flush()

    # Create MaterialColor links for common BambuLab combinations
    # Link basic colors to PLA and PETG material types (most commonly used)
    created_links = 0
    common_material_codes = ["PLA_BASIC", "PLA_MATTE", "PETG_BASIC", "PETG_HF"]
    common_color_codes = ["BLK", "WHT", "GRY", "RED", "BLU", "GRN"]

    for mt_code in common_material_codes:
        if mt_code not in material_type_objs:
            continue
        mt = material_type_objs[mt_code]

        for color_code in common_color_codes:
            if color_code not in color_objs:
                continue
            color = color_objs[color_code]

            # Check if link already exists
            existing_link = db.query(MaterialColor).filter(
                MaterialColor.material_type_id == mt.id,
                MaterialColor.color_id == color.id
            ).first()

            if not existing_link:
                link = MaterialColor(
                    material_type_id=mt.id,
                    color_id=color.id,
                    is_customer_visible=True
                )
                db.add(link)
                created_links += 1

    db.flush()

    print(f"\n  📊 Created {created_types} material types, {created_colors} colors, {created_links} material-color links")
    print("  💡 Tip: Import additional materials via CSV or use 'Create new color' in the material form")

    return created_types, created_colors, created_links, 0  # types, colors, links, products


def main():
    """Main seed function"""
    print("=" * 60)
    print("FilaOps Example Data Seeder")
    print("=" * 60)
    
    db: Session = SessionLocal()
    
    try:
        # Seed example items
        items_created, items_skipped = seed_example_items(db)
        
        # Seed materials (returns products_created as 4th value)
        mt_created, colors_created, links_created, mat_products_created = seed_materials(db)

        db.commit()

        print("\n" + "=" * 60)
        print("✅ Seeding complete!")
        print("=" * 60)
        print("\nSummary:")
        print(f"  📦 Example Items: {items_created} created, {items_skipped} skipped")
        print(f"  🎨 Materials: {mt_created} types, {colors_created} colors, {links_created} links")
        print(f"  📦 Material Products: {mat_products_created} SKUs created (0 on-hand)")
        print("\n💡 Tip: You can now see example items in each category!")
        print("💡 Tip: All material+color combinations are ready - just update inventory quantities!")
        print(f"💡 Tip: Material SKUs follow format: MAT-{'{MATERIAL_CODE}'}-{'{COLOR_CODE}'}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

