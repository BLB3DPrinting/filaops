"""
Seed data for Week 5 UI testing.
Creates products with routings and production orders with operations.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta
from app.db.session import SessionLocal
from app.models.product import Product
from app.models.manufacturing import Routing, RoutingOperation, Resource
from app.models.work_center import WorkCenter
from app.models.production_order import ProductionOrder, ProductionOrderOperation


def seed_data():
    db = SessionLocal()
    
    try:
        print("🌱 Seeding Week 5 test data...")
        
        # Check for existing test data
        existing = db.query(ProductionOrder).filter(ProductionOrder.code.like("PO-TEST-%")).first()
        if existing:
            print("⚠️  Test data already exists. Skipping seed.")
            print("    To re-seed, delete PO-TEST-* records first.")
            return
        
        # --- Work Centers ---
        print("  Creating work centers...")
        wc_print = db.query(WorkCenter).filter(WorkCenter.code == "WC-PRINT").first()
        if not wc_print:
            wc_print = WorkCenter(code="WC-PRINT", name="3D Printing", is_active=True)
            db.add(wc_print)
        
        wc_finish = db.query(WorkCenter).filter(WorkCenter.code == "WC-FINISH").first()
        if not wc_finish:
            wc_finish = WorkCenter(code="WC-FINISH", name="Finishing", is_active=True)
            db.add(wc_finish)
        
        wc_assembly = db.query(WorkCenter).filter(WorkCenter.code == "WC-ASSY").first()
        if not wc_assembly:
            wc_assembly = WorkCenter(code="WC-ASSY", name="Assembly", is_active=True)
            db.add(wc_assembly)
        
        wc_qc = db.query(WorkCenter).filter(WorkCenter.code == "WC-QC").first()
        if not wc_qc:
            wc_qc = WorkCenter(code="WC-QC", name="Quality Control", is_active=True)
            db.add(wc_qc)
        
        wc_ship = db.query(WorkCenter).filter(WorkCenter.code == "WC-SHIP").first()
        if not wc_ship:
            wc_ship = WorkCenter(code="WC-SHIP", name="Shipping", is_active=True)
            db.add(wc_ship)
        
        db.flush()
        
        # --- Resources ---
        print("  Creating resources...")
        res_p1 = db.query(Resource).filter(Resource.code == "P1S-01").first()
        if not res_p1:
            res_p1 = Resource(code="P1S-01", name="Bambu P1S #1", work_center_id=wc_print.id, status="available")
            db.add(res_p1)
        
        res_p2 = db.query(Resource).filter(Resource.code == "P1S-02").first()
        if not res_p2:
            res_p2 = Resource(code="P1S-02", name="Bambu P1S #2", work_center_id=wc_print.id, status="available")
            db.add(res_p2)
        
        res_x1 = db.query(Resource).filter(Resource.code == "X1C-01").first()
        if not res_x1:
            res_x1 = Resource(code="X1C-01", name="Bambu X1C #1", work_center_id=wc_print.id, status="available")
            db.add(res_x1)
        
        res_finish = db.query(Resource).filter(Resource.code == "FINISH-01").first()
        if not res_finish:
            res_finish = Resource(code="FINISH-01", name="Finishing Station", work_center_id=wc_finish.id, status="available")
            db.add(res_finish)
        
        res_assy = db.query(Resource).filter(Resource.code == "ASSY-01").first()
        if not res_assy:
            res_assy = Resource(code="ASSY-01", name="Assembly Bench", work_center_id=wc_assembly.id, status="available")
            db.add(res_assy)
        
        res_qc = db.query(Resource).filter(Resource.code == "QC-01").first()
        if not res_qc:
            res_qc = Resource(code="QC-01", name="QC Station", work_center_id=wc_qc.id, status="available")
            db.add(res_qc)
        
        res_pack = db.query(Resource).filter(Resource.code == "PACK-01").first()
        if not res_pack:
            res_pack = Resource(code="PACK-01", name="Packing Station", work_center_id=wc_ship.id, status="available")
            db.add(res_pack)
        
        db.flush()
        
        # --- Product 1: Simple (2 ops) ---
        print("  Creating Product 1: Simple Widget...")
        prod1 = db.query(Product).filter(Product.sku == "WIDGET-TEST-001").first()
        if not prod1:
            prod1 = Product(
                sku="WIDGET-TEST-001",
                name="Simple Widget (Test)",
                description="A simple 3D printed widget for testing",
                active=True
            )
            db.add(prod1)
            db.flush()
            
            routing1 = Routing(product_id=prod1.id, code="RTG-WIDGET-TEST-001", name="Widget Test Routing", is_active=True)
            db.add(routing1)
            db.flush()
            
            db.add_all([
                RoutingOperation(routing_id=routing1.id, sequence=10, operation_code="PRINT", 
                               operation_name="3D Print", work_center_id=wc_print.id,
                               setup_time_minutes=5, run_time_minutes=45),
                RoutingOperation(routing_id=routing1.id, sequence=20, operation_code="PACK",
                               operation_name="Package", work_center_id=wc_ship.id,
                               setup_time_minutes=2, run_time_minutes=5),
            ])
        
        # --- Product 2: Complex (5 ops) ---
        print("  Creating Product 2: Gadget Pro...")
        prod2 = db.query(Product).filter(Product.sku == "GADGET-TEST-PRO").first()
        if not prod2:
            prod2 = Product(
                sku="GADGET-TEST-PRO",
                name="Gadget Pro (Test)",
                description="Multi-component assembled gadget for testing",
                active=True
            )
            db.add(prod2)
            db.flush()
            
            routing2 = Routing(product_id=prod2.id, code="RTG-GADGET-TEST-PRO", name="Gadget Pro Test Routing", is_active=True)
            db.add(routing2)
            db.flush()
            
            db.add_all([
                RoutingOperation(routing_id=routing2.id, sequence=10, operation_code="PRINT",
                               operation_name="3D Print Components", work_center_id=wc_print.id,
                               setup_time_minutes=10, run_time_minutes=120),
                RoutingOperation(routing_id=routing2.id, sequence=20, operation_code="CLEAN",
                               operation_name="Post-Print Cleanup", work_center_id=wc_finish.id,
                               setup_time_minutes=5, run_time_minutes=15),
                RoutingOperation(routing_id=routing2.id, sequence=30, operation_code="ASSEMBLE",
                               operation_name="Final Assembly", work_center_id=wc_assembly.id,
                               setup_time_minutes=5, run_time_minutes=30),
                RoutingOperation(routing_id=routing2.id, sequence=40, operation_code="QC",
                               operation_name="Quality Inspection", work_center_id=wc_qc.id,
                               setup_time_minutes=2, run_time_minutes=10),
                RoutingOperation(routing_id=routing2.id, sequence=50, operation_code="PACK",
                               operation_name="Pack & Label", work_center_id=wc_ship.id,
                               setup_time_minutes=3, run_time_minutes=8),
            ])
        
        db.flush()
        
        # --- PO 1: Draft (no operations yet) ---
        print("  Creating PO-TEST-001: Draft...")
        po1 = ProductionOrder(
            code="PO-TEST-001",
            product_id=prod1.id,
            quantity_ordered=5,
            status="draft",
            priority=3
        )
        db.add(po1)
        
        # --- PO 2: Released with operations (all pending) ---
        print("  Creating PO-TEST-002: Released, all pending...")
        po2 = ProductionOrder(
            code="PO-TEST-002",
            product_id=prod2.id,
            quantity_ordered=10,
            status="released",
            priority=1
        )
        db.add(po2)
        db.flush()
        
        db.add_all([
            ProductionOrderOperation(production_order_id=po2.id, sequence=10, operation_code="PRINT",
                                    operation_name="3D Print Components", work_center_id=wc_print.id,
                                    planned_setup_minutes=10, planned_run_minutes=1200, status="pending"),
            ProductionOrderOperation(production_order_id=po2.id, sequence=20, operation_code="CLEAN",
                                    operation_name="Post-Print Cleanup", work_center_id=wc_finish.id,
                                    planned_setup_minutes=5, planned_run_minutes=150, status="pending"),
            ProductionOrderOperation(production_order_id=po2.id, sequence=30, operation_code="ASSEMBLE",
                                    operation_name="Final Assembly", work_center_id=wc_assembly.id,
                                    planned_setup_minutes=5, planned_run_minutes=300, status="pending"),
            ProductionOrderOperation(production_order_id=po2.id, sequence=40, operation_code="QC",
                                    operation_name="Quality Inspection", work_center_id=wc_qc.id,
                                    planned_setup_minutes=2, planned_run_minutes=100, status="pending"),
            ProductionOrderOperation(production_order_id=po2.id, sequence=50, operation_code="PACK",
                                    operation_name="Pack & Label", work_center_id=wc_ship.id,
                                    planned_setup_minutes=3, planned_run_minutes=80, status="pending"),
        ])
        
        # --- PO 3: In Progress (mixed states) ---
        print("  Creating PO-TEST-003: In Progress, mixed states...")
        po3 = ProductionOrder(
            code="PO-TEST-003",
            product_id=prod2.id,
            quantity_ordered=5,
            status="in_progress",
            priority=1
        )
        db.add(po3)
        db.flush()
        
        now = datetime.utcnow()
        db.add_all([
            ProductionOrderOperation(production_order_id=po3.id, sequence=10, operation_code="PRINT",
                                    operation_name="3D Print Components", work_center_id=wc_print.id,
                                    resource_id=res_p1.id,
                                    planned_setup_minutes=10, planned_run_minutes=600,
                                    actual_setup_minutes=8, actual_run_minutes=580,
                                    actual_start=now - timedelta(hours=10),
                                    actual_end=now - timedelta(hours=1),
                                    status="complete"),
            ProductionOrderOperation(production_order_id=po3.id, sequence=20, operation_code="CLEAN",
                                    operation_name="Post-Print Cleanup", work_center_id=wc_finish.id,
                                    resource_id=res_finish.id,
                                    planned_setup_minutes=5, planned_run_minutes=75,
                                    actual_start=now - timedelta(minutes=25),
                                    status="running"),
            ProductionOrderOperation(production_order_id=po3.id, sequence=30, operation_code="ASSEMBLE",
                                    operation_name="Final Assembly", work_center_id=wc_assembly.id,
                                    planned_setup_minutes=5, planned_run_minutes=150, status="pending"),
            ProductionOrderOperation(production_order_id=po3.id, sequence=40, operation_code="QC",
                                    operation_name="Quality Inspection", work_center_id=wc_qc.id,
                                    planned_setup_minutes=2, planned_run_minutes=50, status="pending"),
            ProductionOrderOperation(production_order_id=po3.id, sequence=50, operation_code="PACK",
                                    operation_name="Pack & Label", work_center_id=wc_ship.id,
                                    planned_setup_minutes=3, planned_run_minutes=40, status="pending"),
        ])
        
        # --- PO 4: Almost done (with skipped op) ---
        print("  Creating PO-TEST-004: Almost complete, with skipped op...")
        po4 = ProductionOrder(
            code="PO-TEST-004",
            product_id=prod2.id,
            quantity_ordered=3,
            status="in_progress",
            priority=3
        )
        db.add(po4)
        db.flush()
        
        db.add_all([
            ProductionOrderOperation(production_order_id=po4.id, sequence=10, operation_code="PRINT",
                                    operation_name="3D Print Components", work_center_id=wc_print.id,
                                    resource_id=res_x1.id,
                                    planned_setup_minutes=10, planned_run_minutes=360,
                                    actual_setup_minutes=12, actual_run_minutes=340,
                                    actual_start=now - timedelta(hours=8),
                                    actual_end=now - timedelta(hours=2),
                                    status="complete"),
            ProductionOrderOperation(production_order_id=po4.id, sequence=20, operation_code="CLEAN",
                                    operation_name="Post-Print Cleanup", work_center_id=wc_finish.id,
                                    resource_id=res_finish.id,
                                    planned_setup_minutes=5, planned_run_minutes=45,
                                    actual_setup_minutes=5, actual_run_minutes=38,
                                    actual_start=now - timedelta(hours=2),
                                    actual_end=now - timedelta(hours=1, minutes=15),
                                    status="complete"),
            ProductionOrderOperation(production_order_id=po4.id, sequence=30, operation_code="ASSEMBLE",
                                    operation_name="Final Assembly", work_center_id=wc_assembly.id,
                                    planned_setup_minutes=5, planned_run_minutes=90,
                                    notes="Customer provided pre-assembled units",
                                    status="skipped"),
            ProductionOrderOperation(production_order_id=po4.id, sequence=40, operation_code="QC",
                                    operation_name="Quality Inspection", work_center_id=wc_qc.id,
                                    resource_id=res_qc.id,
                                    planned_setup_minutes=2, planned_run_minutes=30,
                                    actual_setup_minutes=2, actual_run_minutes=25,
                                    actual_start=now - timedelta(hours=1),
                                    actual_end=now - timedelta(minutes=30),
                                    status="complete"),
            ProductionOrderOperation(production_order_id=po4.id, sequence=50, operation_code="PACK",
                                    operation_name="Pack & Label", work_center_id=wc_ship.id,
                                    resource_id=res_pack.id,
                                    planned_setup_minutes=3, planned_run_minutes=24,
                                    actual_start=now - timedelta(minutes=15),
                                    status="running"),
        ])
        
        # --- PO 5: Complete ---
        print("  Creating PO-TEST-005: Complete...")
        po5 = ProductionOrder(
            code="PO-TEST-005",
            product_id=prod1.id,
            quantity_ordered=20,
            quantity_completed=20,
            status="complete",
            priority=3
        )
        db.add(po5)
        db.flush()
        
        db.add_all([
            ProductionOrderOperation(production_order_id=po5.id, sequence=10, operation_code="PRINT",
                                    operation_name="3D Print", work_center_id=wc_print.id,
                                    resource_id=res_p2.id,
                                    planned_setup_minutes=5, planned_run_minutes=900,
                                    actual_setup_minutes=5, actual_run_minutes=875,
                                    actual_start=now - timedelta(days=1, hours=16),
                                    actual_end=now - timedelta(days=1, hours=1),
                                    status="complete"),
            ProductionOrderOperation(production_order_id=po5.id, sequence=20, operation_code="PACK",
                                    operation_name="Package", work_center_id=wc_ship.id,
                                    resource_id=res_pack.id,
                                    planned_setup_minutes=2, planned_run_minutes=100,
                                    actual_setup_minutes=2, actual_run_minutes=95,
                                    actual_start=now - timedelta(days=1),
                                    actual_end=now - timedelta(hours=22),
                                    status="complete"),
        ])
        
        db.commit()
        
        print("\n✅ Seed data created successfully!")
        print("\n📋 Test Data Summary:")
        print("=" * 50)
        print("  Work Centers: 5")
        print("  Resources: 7")
        print("  Products: 2")
        print("  Routings: 2")
        print("  Production Orders: 5")
        print("=" * 50)
        print("\n🔍 PO Test Scenarios:")
        print("  PO-TEST-001: Draft (no operations)")
        print("  PO-TEST-002: Released, all pending (5 ops)")
        print("  PO-TEST-003: In Progress - 1 complete, 1 running, 3 pending")
        print("  PO-TEST-004: Almost done - 3 complete, 1 skipped, 1 running")
        print("  PO-TEST-005: Complete (all ops done)")
        print()
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
