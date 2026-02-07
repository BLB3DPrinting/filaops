#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FilaOps - Production Test Data Seeder

Creates comprehensive test data to enable E2E testing and workflow validation:
- Work Centers and Resources (machines/stations)
- Products with BOMs (raw materials, components, assemblies)  
- Production Orders in various states
- Inventory for materials
- Sales Orders to trigger MRP
- Purchase Orders for incoming supply

Usage:
  cd backend
  python scripts/seed_production_test_data.py

This creates realistic manufacturing data for a 3D print farm.
"""
import sys
import os
from decimal import Decimal
from datetime import datetime, date, timedelta

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.core.settings import settings
from app.models import (
    Product, BOM, BOMLine, WorkCenter,
    ProductionOrder, Inventory, InventoryLocation,
    SalesOrder, PurchaseOrder, PurchaseOrderLine,
    ItemCategory, Vendor, User
)
from app.models.manufacturing import Resource

def create_test_data():
    """Create comprehensive test data for production workflows"""
    db = SessionLocal()
    
    try:
        print("🌱 Creating FilaOps Production Test Data...")
        print("=" * 50)
        
        # Get admin user for created_by fields
        admin_user = db.query(User).filter(User.account_type == "admin").first()
        if not admin_user:
            print("❌ No admin user found! Run setup first.")
            return
        
        admin_id = str(admin_user.id)
        
        # ========================================
        # 1. ITEM CATEGORIES
        # ========================================
        print("\n📂 Creating item categories...")
        
        categories = {
            "raw_material": ItemCategory(
                code="RAW_MAT",
                name="Raw Material",
                description="Base materials for production (filament, consumables)"
            ),
            "component": ItemCategory(
                code="COMPONENT",
                name="Component", 
                description="Manufactured parts and hardware"
            ),
            "assembly": ItemCategory(
                code="ASSEMBLY",
                name="Assembly",
                description="Multi-component finished goods"
            ),
            "packaging": ItemCategory(
                code="PACKAGING",
                name="Packaging",
                description="Shipping materials and packaging"
            )
        }
        
        for cat_key, category in categories.items():
            existing = db.query(ItemCategory).filter(ItemCategory.name == category.name).first()
            if not existing:
                db.add(category)
                print(f"   ✅ Created category: {category.name}")
        
        db.flush()
        
        # Refresh category references
        for cat_key in categories.keys():
            categories[cat_key] = db.query(ItemCategory).filter(
                ItemCategory.name == categories[cat_key].name
            ).first()
        
        # ========================================
        # 2. WORK CENTERS & MACHINES
        # ========================================
        print("\n🏭 Creating work centers and machines...")
        
        # 3D Printer Work Center
        printer_wc = WorkCenter(
            code="WC-PRINT",
            name="3D Printer Pool",
            description="FDM 3D Printers for production",
            hourly_rate=Decimal("15.00")
        )
        
        # Assembly Work Center  
        assembly_wc = WorkCenter(
            code="WC-ASM",
            name="Assembly Station",
            description="Manual assembly and finishing",
            hourly_rate=Decimal("25.00")
        )
        
        existing_printer_wc = db.query(WorkCenter).filter(WorkCenter.name == "3D Printer Pool").first()
        existing_assembly_wc = db.query(WorkCenter).filter(WorkCenter.name == "Assembly Station").first()
        
        if not existing_printer_wc:
            db.add(printer_wc)
            print("   ✅ Created work center: 3D Printer Pool")
        else:
            printer_wc = existing_printer_wc
            
        if not existing_assembly_wc:
            db.add(assembly_wc)
            print("   ✅ Created work center: Assembly Station")
        else:
            assembly_wc = existing_assembly_wc
            
        db.flush()
        
        # Create machines
        machines = [
            {
                "code": "PRINTER-001",
                "name": "Printer-001",
                "description": "Bambu Lab X1 Carbon #1",
                "work_center": printer_wc,
                "status": "available",
                "machine_type": "3d_printer"
            },
            {
                "code": "PRINTER-002",
                "name": "Printer-002", 
                "description": "Bambu Lab X1 Carbon #2",
                "work_center": printer_wc,
                "status": "busy",
                "machine_type": "3d_printer"
            },
            {
                "code": "PRINTER-003",
                "name": "Printer-003",
                "description": "Prusa MK4 #1",
                "work_center": printer_wc,
                "status": "maintenance",
                "machine_type": "3d_printer"
            },
            {
                "code": "ASM-001",
                "name": "Assembly-001",
                "description": "Manual Assembly Station #1", 
                "work_center": assembly_wc,
                "status": "available",
                "machine_type": "assembly_station"
            }
        ]
        
        for machine_data in machines:
            existing = db.query(Resource).filter(Resource.name == machine_data["name"]).first()
            if not existing:
                machine = Resource(
                    code=machine_data["code"],
                    name=machine_data["name"],
                    work_center_id=machine_data["work_center"].id,
                    status=machine_data["status"],
                    machine_type=machine_data["machine_type"]
                )
                db.add(machine)
                print(f"   ✅ Created machine: {machine_data['name']}")
        
        # ========================================
        # 3. VENDORS
        # ========================================
        print("\n🏪 Creating vendors...")
        
        vendors_data = [
            {
                "code": "POLY-001",
                "name": "Polymaker Supply Co",
                "email": "orders@polymaker.com",
                "notes": "Premium filament supplier"
            },
            {
                "code": "MCM-001",
                "name": "McMaster Hardware", 
                "email": "orders@mcmaster.com",
                "notes": "Fasteners and hardware"
            },
            {
                "code": "PKG-001",
                "name": "Packaging Solutions Inc",
                "email": "sales@packagesolutions.com", 
                "notes": "Shipping and packaging materials"
            }
        ]
        
        vendors = {}
        for vendor_data in vendors_data:
            existing = db.query(Vendor).filter(Vendor.name == vendor_data["name"]).first()
            if not existing:
                vendor = Vendor(
                    code=vendor_data["code"],
                    name=vendor_data["name"],
                    email=vendor_data["email"],
                    notes=vendor_data["notes"]
                )
                db.add(vendor)
                vendors[vendor_data["name"]] = vendor
                print(f"   ✅ Created vendor: {vendor_data['name']}")
            else:
                vendors[vendor_data["name"]] = existing
        
        db.flush()
        
        # ========================================
        # 4. INVENTORY LOCATIONS
        # ========================================
        print("\n📍 Creating inventory locations...")
        
        locations_data = [
            {"code": "MAIN", "name": "Main Warehouse", "type": "warehouse"},
            {"code": "PROD", "name": "Production Floor", "type": "work_area"},
            {"code": "SHIP", "name": "Shipping", "type": "shipping_area"}
        ]
        
        locations = {}
        for loc_data in locations_data:
            existing = db.query(InventoryLocation).filter(
                InventoryLocation.name == loc_data["name"]
            ).first()
            if not existing:
                location = InventoryLocation(
                    code=loc_data["code"],
                    name=loc_data["name"],
                    type=loc_data["type"]
                )
                db.add(location)
                locations[loc_data["name"]] = location
                print(f"   ✅ Created location: {loc_data['name']}")
            else:
                locations[loc_data["name"]] = existing
                
        db.flush()
        
        # ========================================
        # 5. PRODUCTS (Raw Materials, Components, Assemblies)
        # ========================================
        print("\n🔧 Creating products...")
        
        products_data = [
            # Raw Materials
            {
                "sku": "PLA-BLK-1KG",
                "name": "PLA Filament Black 1kg",
                "item_type": "supply", 
                "category": categories["raw_material"],
                "unit": "KG",
                "procurement_type": "buy",
                "standard_cost": Decimal("25.00"),
                "safety_stock": Decimal("5.0"),
                "reorder_point": Decimal("10.0"),
                "min_order_qty": Decimal("10.0"),
                "lead_time_days": 7
            },
            {
                "sku": "PLA-WHT-1KG",
                "name": "PLA Filament White 1kg", 
                "item_type": "supply",
                "category": categories["raw_material"],
                "unit": "KG",
                "procurement_type": "buy",
                "standard_cost": Decimal("25.00"),
                "safety_stock": Decimal("5.0"),
                "reorder_point": Decimal("10.0"),
                "min_order_qty": Decimal("10.0"),
                "lead_time_days": 7
            },
            {
                "sku": "SCREW-M3X10",
                "name": "M3x10mm Socket Head Cap Screw",
                "item_type": "component",
                "category": categories["raw_material"], 
                "unit": "EA",
                "procurement_type": "buy",
                "standard_cost": Decimal("0.15"),
                "safety_stock": Decimal("100"),
                "reorder_point": Decimal("500"),
                "min_order_qty": Decimal("1000"),
                "lead_time_days": 14
            },
            
            # Components (Manufactured)
            {
                "sku": "BRACKET-001",
                "name": "Mounting Bracket V1",
                "item_type": "component",
                "category": categories["component"],
                "unit": "EA",
                "procurement_type": "make",
                "has_bom": True,
                "standard_cost": Decimal("2.50"),
                "safety_stock": Decimal("10"),
                "reorder_point": Decimal("25"),
                "min_order_qty": Decimal("50"),
                "lead_time_days": 3
            },
            {
                "sku": "HOUSING-001", 
                "name": "Electronic Housing",
                "item_type": "component",
                "category": categories["component"],
                "unit": "EA",
                "procurement_type": "make",
                "has_bom": True,
                "standard_cost": Decimal("4.25"),
                "safety_stock": Decimal("5"),
                "reorder_point": Decimal("15"),
                "min_order_qty": Decimal("25"),
                "lead_time_days": 5
            },
            
            # Assemblies (Multi-component finished goods)
            {
                "sku": "ASM-SENSOR-KIT", 
                "name": "Sensor Assembly Kit",
                "item_type": "finished_good",
                "category": categories["assembly"],
                "unit": "EA",
                "procurement_type": "make",
                "has_bom": True,
                "selling_price": Decimal("49.99"),
                "standard_cost": Decimal("18.50"),
                "safety_stock": Decimal("2"),
                "reorder_point": Decimal("5"),
                "min_order_qty": Decimal("5"),
                "lead_time_days": 7
            },
            
            # Packaging Materials
            {
                "sku": "BOX-SMALL",
                "name": "Small Shipping Box",
                "item_type": "supply",
                "category": categories["packaging"],
                "unit": "EA",
                "procurement_type": "buy",
                "standard_cost": Decimal(str(settings.MACHINE_HOURLY_RATE)),
                "safety_stock": Decimal("50"),
                "reorder_point": Decimal("100"),
                "min_order_qty": Decimal("250"),
                "lead_time_days": 10
            },
            {
                "sku": "BUBBLE-WRAP",
                "name": "Bubble Wrap Roll",
                "item_type": "supply",
                "category": categories["packaging"], 
                "unit": "ROLL",
                "procurement_type": "buy",
                "standard_cost": Decimal("12.00"),
                "safety_stock": Decimal("5"),
                "reorder_point": Decimal("10"),
                "min_order_qty": Decimal("20"),
                "lead_time_days": 7
            }
        ]
        
        products = {}
        for product_data in products_data:
            existing = db.query(Product).filter(Product.sku == product_data["sku"]).first()
            if not existing:
                product = Product(
                    sku=product_data["sku"],
                    name=product_data["name"],
                    item_type=product_data["item_type"],
                    category_id=product_data["category"].id,
                    unit=product_data["unit"],
                    procurement_type=product_data["procurement_type"],
                    has_bom=product_data.get("has_bom", False),
                    selling_price=product_data.get("selling_price"),
                    standard_cost=product_data["standard_cost"],
                    safety_stock=product_data["safety_stock"],
                    reorder_point=product_data["reorder_point"],
                    min_order_qty=product_data["min_order_qty"],
                    lead_time_days=product_data["lead_time_days"]
                )
                db.add(product)
                products[product_data["sku"]] = product
                print(f"   ✅ Created product: {product_data['sku']} - {product_data['name']}")
            else:
                products[product_data["sku"]] = existing
        
        db.flush()
        
        # ========================================
        # 6. BILLS OF MATERIALS
        # ========================================
        print("\n📋 Creating Bills of Materials...")
        
        bom_data = [
            {
                "product_sku": "BRACKET-001",
                "description": "Simple 3D printed bracket",
                "lines": [
                    {"component_sku": "PLA-BLK-1KG", "quantity": Decimal("0.025"), "unit": "KG"},
                    {"component_sku": "BOX-SMALL", "quantity": Decimal("1"), "unit": "EA"}
                ]
            },
            {
                "product_sku": "HOUSING-001", 
                "description": "Electronic housing with fasteners",
                "lines": [
                    {"component_sku": "PLA-BLK-1KG", "quantity": Decimal("0.045"), "unit": "KG"},
                    {"component_sku": "SCREW-M3X10", "quantity": Decimal("4"), "unit": "EA"},
                    {"component_sku": "BOX-SMALL", "quantity": Decimal("1"), "unit": "EA"},
                    {"component_sku": "BUBBLE-WRAP", "quantity": Decimal("0.1"), "unit": "ROLL"}
                ]
            },
            {
                "product_sku": "ASM-SENSOR-KIT",
                "description": "Multi-component sensor assembly",
                "lines": [
                    {"component_sku": "BRACKET-001", "quantity": Decimal("2"), "unit": "EA"},
                    {"component_sku": "HOUSING-001", "quantity": Decimal("1"), "unit": "EA"},
                    {"component_sku": "SCREW-M3X10", "quantity": Decimal("8"), "unit": "EA"},
                    {"component_sku": "BOX-SMALL", "quantity": Decimal("1"), "unit": "EA"},
                    {"component_sku": "BUBBLE-WRAP", "quantity": Decimal("0.2"), "unit": "ROLL"}
                ]
            }
        ]
        
        boms = {}
        for bom_spec in bom_data:
            product = products[bom_spec["product_sku"]]
            
            existing_bom = db.query(BOM).filter(
                BOM.product_id == product.id, BOM.active == True
            ).first()
            
            if not existing_bom:
                bom = BOM(
                    product_id=product.id,
                    notes=bom_spec["description"],
                    active=True
                )
                db.add(bom)
                db.flush()
                
                # Add BOM lines
                for line_spec in bom_spec["lines"]:
                    component = products[line_spec["component_sku"]]
                    
                    bom_line = BOMLine(
                        bom_id=bom.id,
                        component_id=component.id,
                        quantity=line_spec["quantity"],
                        unit=line_spec["unit"]
                    )
                    db.add(bom_line)
                
                boms[bom_spec["product_sku"]] = bom
                print(f"   ✅ Created BOM: {bom_spec['product_sku']} ({len(bom_spec['lines'])} lines)")
            else:
                boms[bom_spec["product_sku"]] = existing_bom
        
        # ========================================
        # 7. INVENTORY
        # ========================================
        print("\n📦 Creating inventory...")
        
        inventory_data = [
            # Raw materials - good stock levels
            {"product_sku": "PLA-BLK-1KG", "location": "Main Warehouse", "on_hand": Decimal("45.5"), "allocated": Decimal("5.0")},
            {"product_sku": "PLA-WHT-1KG", "location": "Main Warehouse", "on_hand": Decimal("32.8"), "allocated": Decimal("2.5")},
            {"product_sku": "SCREW-M3X10", "location": "Main Warehouse", "on_hand": Decimal("2500"), "allocated": Decimal("200")},
            
            # Packaging materials
            {"product_sku": "BOX-SMALL", "location": "Shipping", "on_hand": Decimal("150"), "allocated": Decimal("10")},
            {"product_sku": "BUBBLE-WRAP", "location": "Shipping", "on_hand": Decimal("8"), "allocated": Decimal("1")},
            
            # Manufactured components - some shortages to trigger MRP
            {"product_sku": "BRACKET-001", "location": "Production Floor", "on_hand": Decimal("15"), "allocated": Decimal("5")},
            {"product_sku": "HOUSING-001", "location": "Production Floor", "on_hand": Decimal("8"), "allocated": Decimal("3")},
            
            # Finished assemblies - low stock
            {"product_sku": "ASM-SENSOR-KIT", "location": "Main Warehouse", "on_hand": Decimal("3"), "allocated": Decimal("1")}
        ]
        
        for inv_data in inventory_data:
            product = products[inv_data["product_sku"]]
            location = locations[inv_data["location"]]
            
            existing = db.query(Inventory).filter(
                Inventory.product_id == product.id,
                Inventory.location_id == location.id
            ).first()
            
            if not existing:
                inventory = Inventory(
                    product_id=product.id,
                    location_id=location.id,
                    on_hand_quantity=inv_data["on_hand"],
                    allocated_quantity=inv_data["allocated"]
                )
                db.add(inventory)
                print(f"   ✅ Inventory: {inv_data['product_sku']} = {inv_data['on_hand']} @ {inv_data['location']}")
        
        # ========================================
        # 8. PRODUCTION ORDERS
        # ========================================
        print("\n🏭 Creating production orders...")
        
        production_orders_data = [
            {
                "code": "WO-2024-0001",
                "product_sku": "BRACKET-001", 
                "quantity": Decimal("50"),
                "status": "draft",
                "due_date": date.today() + timedelta(days=7),
                "notes": "Initial bracket production run"
            },
            {
                "code": "WO-2024-0002",
                "product_sku": "HOUSING-001",
                "quantity": Decimal("25"), 
                "status": "released",
                "due_date": date.today() + timedelta(days=5),
                "notes": "Housing production for sensor kits"
            },
            {
                "code": "WO-2024-0003",
                "product_sku": "ASM-SENSOR-KIT",
                "quantity": Decimal("10"),
                "status": "in_progress",
                "due_date": date.today() + timedelta(days=10),
                "actual_start": datetime.now() - timedelta(hours=6),
                "quantity_completed": Decimal("3"),
                "notes": "Customer order fulfillment"
            },
            {
                "code": "WO-2024-0004", 
                "product_sku": "BRACKET-001",
                "quantity": Decimal("100"),
                "status": "completed",
                "due_date": date.today() - timedelta(days=2),
                "actual_start": datetime.now() - timedelta(days=5),
                "actual_end": datetime.now() - timedelta(days=1),
                "quantity_completed": Decimal("98"),
                "quantity_scrapped": Decimal("2"),
                "notes": "Completed bracket batch"
            }
        ]
        
        for po_data in production_orders_data:
            existing = db.query(ProductionOrder).filter(
                ProductionOrder.code == po_data["code"]
            ).first()
            
            if not existing:
                product = products[po_data["product_sku"]]
                bom = boms.get(po_data["product_sku"])
                
                production_order = ProductionOrder(
                    code=po_data["code"],
                    product_id=product.id,
                    bom_id=bom.id if bom else None,
                    quantity_ordered=po_data["quantity"],
                    status=po_data["status"],
                    due_date=po_data["due_date"],
                    actual_start=po_data.get("actual_start"),
                    actual_end=po_data.get("actual_end"),
                    quantity_completed=po_data.get("quantity_completed", Decimal("0")),
                    quantity_scrapped=po_data.get("quantity_scrapped", Decimal("0")),
                    source="manual",
                    notes=po_data["notes"]
                )
                db.add(production_order)
                print(f"   ✅ Production Order: {po_data['code']} - {po_data['status']}")
        
        # ========================================
        # 9. PURCHASE ORDERS
        # ========================================
        print("\n🛒 Creating purchase orders...")
        
        purchase_orders_data = [
            {
                "po_number": "PO-2024-0001",
                "vendor_name": "Polymaker Supply Co",
                "status": "ordered",
                "order_date": date.today() - timedelta(days=3),
                "expected_date": date.today() + timedelta(days=4),
                "lines": [
                    {"product_sku": "PLA-BLK-1KG", "quantity": Decimal("20"), "unit_cost": Decimal("24.50"), "received": Decimal("0")},
                    {"product_sku": "PLA-WHT-1KG", "quantity": Decimal("15"), "unit_cost": Decimal("24.50"), "received": Decimal("0")}
                ]
            },
            {
                "po_number": "PO-2024-0002", 
                "vendor_name": "McMaster Hardware",
                "status": "partially_received",
                "order_date": date.today() - timedelta(days=7),
                "expected_date": date.today() - timedelta(days=1),
                "lines": [
                    {"product_sku": "SCREW-M3X10", "quantity": Decimal("5000"), "unit_cost": Decimal("0.12"), "received": Decimal("3000")}
                ]
            }
        ]
        
        for po_data in purchase_orders_data:
            existing = db.query(PurchaseOrder).filter(
                PurchaseOrder.po_number == po_data["po_number"]
            ).first()
            
            if not existing:
                vendor = vendors[po_data["vendor_name"]]
                
                # Calculate totals
                subtotal = sum(
                    line["quantity"] * line["unit_cost"] 
                    for line in po_data["lines"]
                )
                
                purchase_order = PurchaseOrder(
                    po_number=po_data["po_number"],
                    vendor_id=vendor.id,
                    status=po_data["status"],
                    order_date=po_data["order_date"],
                    expected_date=po_data["expected_date"],
                    subtotal=subtotal,
                    total_amount=subtotal
                )
                db.add(purchase_order)
                db.flush()
                
                # Add PO lines
                for line_num, line_data in enumerate(po_data["lines"], 1):
                    product = products[line_data["product_sku"]]
                    
                    po_line = PurchaseOrderLine(
                        purchase_order_id=purchase_order.id,
                        product_id=product.id,
                        line_number=line_num,
                        quantity_ordered=line_data["quantity"],
                        quantity_received=line_data["received"],
                        unit_cost=line_data["unit_cost"],
                        line_total=line_data["quantity"] * line_data["unit_cost"]
                    )
                    db.add(po_line)
                
                print(f"   ✅ Purchase Order: {po_data['po_number']} - {po_data['status']}")
        
        # ========================================
        # 10. SALES ORDERS (to trigger MRP)
        # ========================================
        print("\n💰 Creating sales orders...")
        
        sales_orders_data = [
            {
                "order_number": "SO-2024-0001",
                "product_sku": "ASM-SENSOR-KIT",
                "quantity": 5,
                "unit_price": Decimal("49.99"),
                "status": "confirmed",
                "estimated_completion": datetime.now() + timedelta(days=14),
                "customer_info": {
                    "first_name": "John",
                    "last_name": "Smith", 
                    "email": "john@example.com"
                }
            },
            {
                "order_number": "SO-2024-0002",
                "product_sku": "BRACKET-001", 
                "quantity": 25,
                "unit_price": Decimal("15.99"),
                "status": "pending_payment",
                "estimated_completion": datetime.now() + timedelta(days=7),
                "customer_info": {
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "email": "jane@example.com"
                }
            }
        ]
        
        for so_data in sales_orders_data:
            existing = db.query(SalesOrder).filter(
                SalesOrder.order_number == so_data["order_number"]
            ).first()
            
            if not existing:
                product = products[so_data["product_sku"]]
                total_price = so_data["quantity"] * so_data["unit_price"]
                
                sales_order = SalesOrder(
                    order_number=so_data["order_number"],
                    user_id=admin_user.id,
                    product_id=product.id,
                    product_name=product.name,
                    quantity=so_data["quantity"],
                    unit_price=so_data["unit_price"],
                    total_price=total_price,
                    grand_total=total_price,
                    status=so_data["status"],
                    payment_status="pending",
                    fulfillment_status="pending",
                    estimated_completion_date=so_data["estimated_completion"],
                    material_type="PLA",
                    customer_notes=f"Customer: {so_data['customer_info']['first_name']} {so_data['customer_info']['last_name']} ({so_data['customer_info']['email']})"
                )
                db.add(sales_order)
                print(f"   ✅ Sales Order: {so_data['order_number']} - {so_data['status']}")
        
        # ========================================
        # COMMIT TRANSACTION
        # ========================================
        db.commit()
        print("\n" + "=" * 50)
        print("🎉 PRODUCTION TEST DATA CREATED SUCCESSFULLY!")
        print("=" * 50)
        
        # Summary
        print("\n📊 Data Summary:")
        print(f"   • Products: {len(products_data)}")
        print(f"   • BOMs: {len(bom_data)}")
        print(f"   • Production Orders: {len(production_orders_data)}")
        print(f"   • Purchase Orders: {len(purchase_orders_data)}")
        print(f"   • Sales Orders: {len(sales_orders_data)}")
        print(f"   • Work Centers: 2")
        print(f"   • Resources: 4")
        print(f"   • Vendors: {len(vendors_data)}")
        print(f"   • Inventory Locations: {len(locations_data)}")
        
        print("\n🔬 Ready for Testing:")
        print("   ✅ Production workflow (Draft → Released → In Progress → Complete)")
        print("   ✅ BOM explosion and material requirements")
        print("   ✅ Inventory allocation and consumption")
        print("   ✅ MRP calculations (shortages and planned orders)")
        print("   ✅ Scheduling and capacity planning")
        print("   ✅ Purchase order receiving workflow")
        print("   ✅ Multi-level assembly manufacturing")
        
        print(f"\n🌐 Frontend URLs to test:")
        print(f"   • Production: http://localhost:5173/admin/production")
        print(f"   • Items: http://localhost:5173/admin/items")
        print(f"   • Purchasing: http://localhost:5173/admin/purchasing")
        print(f"   • BOMs: http://localhost:5173/admin/bom")
        
    except Exception as e:
        print(f"\n❌ Error creating test data: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    create_test_data()
