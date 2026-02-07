#!/usr/bin/env python3
"""
FilaOps Database Integrity Checker and Auto-Repair

This script checks and fixes common database issues that can cause:
- MRP calculation failures
- UOM conversion errors  
- Foreign key constraint violations
- Orphaned records
- Performance degradation

Usage:
  cd backend
  python scripts/database_integrity_check.py

Run this before major operations or when experiencing issues.
"""
import sys
import os
from decimal import Decimal
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models import (
    Product, BOM, BOMLine, Inventory, ProductionOrder,
    SalesOrder, PurchaseOrder, PurchaseOrderLine, PlannedOrder,
    ItemCategory, Vendor, User, WorkCenter
)
from sqlalchemy import text, func
from sqlalchemy.orm import sessionmaker

class DatabaseIntegrityChecker:
    """Comprehensive database integrity checker and auto-repair"""
    
    def __init__(self):
        self.db = SessionLocal()
        self.issues_found = []
        self.repairs_made = []
        
    def run_full_check(self, auto_repair=True):
        """Run all integrity checks and optionally auto-repair issues"""
        print("🔍 FilaOps Database Integrity Check")
        print("=" * 50)
        
        # Core data integrity
        self.check_missing_categories()
        self.check_orphaned_products()
        self.check_invalid_bom_references()
        self.check_inventory_inconsistencies()
        
        # Manufacturing data
        self.check_production_order_integrity() 
        self.check_purchase_order_integrity()
        self.check_planned_order_cleanup()
        
        # UOM and conversion issues
        self.check_uom_consistency()
        self.check_quantity_anomalies()
        
        # Performance issues
        self.check_database_statistics()
        self.check_index_health()
        
        # Auto-repair if requested
        if auto_repair and self.issues_found:
            print(f"\n🔧 Auto-repairing {len(self.issues_found)} issues...")
            self.auto_repair_issues()
        
        # Summary
        self.print_summary()
        
    def check_missing_categories(self):
        """Check for products without categories"""
        print("\n📂 Checking product categories...")
        
        products_without_category = self.db.query(Product).filter(
            Product.category_id.is_(None)
        ).all()
        
        if products_without_category:
            self.issues_found.append({
                'type': 'missing_category',
                'count': len(products_without_category),
                'products': products_without_category
            })
            print(f"   ⚠️  {len(products_without_category)} products missing categories")
        else:
            print("   ✅ All products have categories")
            
    def check_orphaned_products(self):
        """Check for products referenced in BOMs but don't exist"""
        print("\n🔗 Checking orphaned product references...")
        
        # Products referenced in BOM lines but don't exist
        orphaned_bom_components = self.db.query(BOMLine).join(
            Product, BOMLine.component_id == Product.id, isouter=True
        ).filter(Product.id.is_(None)).all()
        
        if orphaned_bom_components:
            self.issues_found.append({
                'type': 'orphaned_bom_components',
                'count': len(orphaned_bom_components),
                'bom_lines': orphaned_bom_components
            })
            print(f"   ⚠️  {len(orphaned_bom_components)} BOM lines reference missing products")
        else:
            print("   ✅ No orphaned BOM component references")
            
    def check_invalid_bom_references(self):
        """Check for invalid BOM relationships"""
        print("\n📋 Checking BOM integrity...")
        
        # BOMs without any lines
        empty_boms = self.db.query(BOM).outerjoin(BOMLine).filter(
            BOMLine.id.is_(None)
        ).all()
        
        if empty_boms:
            self.issues_found.append({
                'type': 'empty_boms',
                'count': len(empty_boms),
                'boms': empty_boms
            })
            print(f"   ⚠️  {len(empty_boms)} BOMs have no lines")
        
        # Products marked has_bom=True but no active BOM
        products_missing_boms = self.db.query(Product).filter(
            Product.has_bom == True
        ).outerjoin(BOM, (BOM.product_id == Product.id) & (BOM.active == True)).filter(
            BOM.id.is_(None)
        ).all()
        
        if products_missing_boms:
            self.issues_found.append({
                'type': 'missing_boms',
                'count': len(products_missing_boms),
                'products': products_missing_boms
            })
            print(f"   ⚠️  {len(products_missing_boms)} products marked has_bom=True but no active BOM")
        
        if not empty_boms and not products_missing_boms:
            print("   ✅ BOM integrity looks good")
            
    def check_inventory_inconsistencies(self):
        """Check for inventory data issues"""
        print("\n📦 Checking inventory integrity...")
        
        issues = []
        
        # Negative on-hand quantities
        negative_inventory = self.db.query(Inventory).filter(
            Inventory.on_hand_quantity < 0
        ).all()
        
        if negative_inventory:
            issues.append(f"{len(negative_inventory)} negative on-hand quantities")
            self.issues_found.append({
                'type': 'negative_inventory',
                'count': len(negative_inventory),
                'records': negative_inventory
            })
        
        # Allocated > On-hand
        over_allocated = self.db.query(Inventory).filter(
            Inventory.allocated_quantity > Inventory.on_hand_quantity
        ).all()
        
        if over_allocated:
            issues.append(f"{len(over_allocated)} over-allocated inventory")
            self.issues_found.append({
                'type': 'over_allocated',
                'count': len(over_allocated),
                'records': over_allocated
            })
        
        # Inventory for non-existent products
        orphaned_inventory = self.db.query(Inventory).join(
            Product, Inventory.product_id == Product.id, isouter=True
        ).filter(Product.id.is_(None)).all()
        
        if orphaned_inventory:
            issues.append(f"{len(orphaned_inventory)} orphaned inventory records")
            self.issues_found.append({
                'type': 'orphaned_inventory',
                'count': len(orphaned_inventory),
                'records': orphaned_inventory
            })
        
        if issues:
            print(f"   ⚠️  Issues found: {', '.join(issues)}")
        else:
            print("   ✅ Inventory integrity looks good")
            
    def check_production_order_integrity(self):
        """Check production order data consistency"""
        print("\n🏭 Checking production orders...")
        
        issues = []
        
        # Completed > Ordered
        over_completed = self.db.query(ProductionOrder).filter(
            ProductionOrder.quantity_completed > ProductionOrder.quantity_ordered
        ).all()
        
        if over_completed:
            issues.append(f"{len(over_completed)} over-completed orders")
            self.issues_found.append({
                'type': 'over_completed_po',
                'count': len(over_completed),
                'orders': over_completed
            })
        
        # Production orders for non-existent products
        orphaned_pos = self.db.query(ProductionOrder).join(
            Product, ProductionOrder.product_id == Product.id, isouter=True
        ).filter(Product.id.is_(None)).all()
        
        if orphaned_pos:
            issues.append(f"{len(orphaned_pos)} orphaned production orders")
            self.issues_found.append({
                'type': 'orphaned_production_orders',
                'count': len(orphaned_pos),
                'orders': orphaned_pos
            })
        
        # Invalid status combinations
        invalid_status = self.db.query(ProductionOrder).filter(
            (ProductionOrder.status == 'completed') & 
            (ProductionOrder.actual_completion.is_(None))
        ).all()
        
        if invalid_status:
            issues.append(f"{len(invalid_status)} completed orders missing completion date")
            self.issues_found.append({
                'type': 'invalid_po_status',
                'count': len(invalid_status),
                'orders': invalid_status
            })
        
        if issues:
            print(f"   ⚠️  Issues found: {', '.join(issues)}")
        else:
            print("   ✅ Production order integrity looks good")
            
    def check_purchase_order_integrity(self):
        """Check purchase order data consistency"""
        print("\n🛒 Checking purchase orders...")
        
        issues = []
        
        # PO lines with received > ordered
        over_received = self.db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.quantity_received > PurchaseOrderLine.quantity_ordered
        ).all()
        
        if over_received:
            issues.append(f"{len(over_received)} over-received PO lines")
            self.issues_found.append({
                'type': 'over_received_po_lines',
                'count': len(over_received),
                'lines': over_received
            })
        
        # PO lines for non-existent products
        orphaned_po_lines = self.db.query(PurchaseOrderLine).join(
            Product, PurchaseOrderLine.product_id == Product.id, isouter=True
        ).filter(Product.id.is_(None)).all()
        
        if orphaned_po_lines:
            issues.append(f"{len(orphaned_po_lines)} orphaned PO lines")
            self.issues_found.append({
                'type': 'orphaned_po_lines',
                'count': len(orphaned_po_lines),
                'lines': orphaned_po_lines
            })
        
        if issues:
            print(f"   ⚠️  Issues found: {', '.join(issues)}")
        else:
            print("   ✅ Purchase order integrity looks good")
            
    def check_planned_order_cleanup(self):
        """Check for stale planned orders"""
        print("\n📋 Checking planned orders...")
        
        # Old completed MRP runs with planned orders still present
        stale_planned = self.db.query(PlannedOrder).join(
            Product, PlannedOrder.product_id == Product.id, isouter=True
        ).filter(Product.id.is_(None)).all()
        
        if stale_planned:
            self.issues_found.append({
                'type': 'stale_planned_orders',
                'count': len(stale_planned),
                'orders': stale_planned
            })
            print(f"   ⚠️  {len(stale_planned)} stale planned orders")
        else:
            print("   ✅ Planned orders look clean")
            
    def check_uom_consistency(self):
        """Check for UOM-related issues"""
        print("\n📏 Checking UOM consistency...")
        
        issues = []
        
        # Products with empty/null units
        missing_units = self.db.query(Product).filter(
            (Product.unit.is_(None)) | (Product.unit == '')
        ).all()
        
        if missing_units:
            issues.append(f"{len(missing_units)} products missing units")
            self.issues_found.append({
                'type': 'missing_uom',
                'count': len(missing_units),
                'products': missing_units
            })
        
        # BOM lines with mismatched units (advanced check)
        bom_lines_unit_mismatch = self.db.query(BOMLine).join(
            Product, BOMLine.component_id == Product.id
        ).filter(
            (BOMLine.unit != Product.unit) &
            (BOMLine.unit.isnot(None)) &
            (Product.unit.isnot(None))
        ).all()
        
        # This is actually OK - BOM can specify different units than product base
        # But log for awareness
        if bom_lines_unit_mismatch:
            print(f"   ℹ️  {len(bom_lines_unit_mismatch)} BOM lines use different units than component base unit (this may be intentional)")
        
        if issues:
            print(f"   ⚠️  Issues found: {', '.join(issues)}")
        else:
            print("   ✅ UOM consistency looks good")
            
    def check_quantity_anomalies(self):
        """Check for unrealistic quantity values"""
        print("\n🔢 Checking for quantity anomalies...")
        
        issues = []
        
        # Extremely large quantities (potential data entry errors)
        large_inventory = self.db.query(Inventory).filter(
            Inventory.on_hand_quantity > 1000000
        ).all()
        
        if large_inventory:
            issues.append(f"{len(large_inventory)} suspiciously large inventory quantities")
            
        # Zero/negative costs
        zero_cost_products = self.db.query(Product).filter(
            (Product.standard_cost <= 0) & (Product.item_type.in_(['raw_material', 'component']))
        ).all()
        
        if zero_cost_products:
            issues.append(f"{len(zero_cost_products)} products with zero/negative costs")
            self.issues_found.append({
                'type': 'zero_cost_products',
                'count': len(zero_cost_products),
                'products': zero_cost_products
            })
        
        if issues:
            print(f"   ⚠️  Issues found: {', '.join(issues)}")
        else:
            print("   ✅ Quantity values look reasonable")
            
    def check_database_statistics(self):
        """Check database performance statistics"""
        print("\n📊 Checking database statistics...")
        
        try:
            # Table row counts
            product_count = self.db.query(Product).count()
            bom_count = self.db.query(BOM).count()
            inventory_count = self.db.query(Inventory).count()
            po_count = self.db.query(ProductionOrder).count()
            
            print(f"   📈 Table sizes:")
            print(f"      Products: {product_count:,}")
            print(f"      BOMs: {bom_count:,}")
            print(f"      Inventory records: {inventory_count:,}")
            print(f"      Production orders: {po_count:,}")
            
            # Check for performance red flags
            if inventory_count > 50000:
                print(f"   ⚠️  Large inventory table may impact MRP performance")
                
            if bom_count > product_count * 0.8:
                print(f"   ⚠️  High BOM ratio may indicate deep/complex product structures")
                
        except Exception as e:
            print(f"   ⚠️  Could not gather statistics: {e}")
            
    def check_index_health(self):
        """Check database index status (PostgreSQL specific)"""
        print("\n🔍 Checking index health...")
        
        try:
            # This is PostgreSQL specific - adapt for other databases
            index_check = self.db.execute(text("""
                SELECT 
                    OBJECT_NAME(i.object_id) as table_name,
                    i.name as index_name,
                    i.type_desc,
                    i.is_disabled
                FROM sys.indexes i
                WHERE OBJECT_NAME(i.object_id) IN ('products', 'bom_lines', 'inventory', 'production_orders')
                AND i.is_disabled = 1
            """)).fetchall()
            
            if index_check:
                print(f"   ⚠️  {len(index_check)} disabled indexes found")
                for row in index_check:
                    print(f"      {row.table_name}.{row.index_name}")
            else:
                print("   ✅ Indexes are healthy")
                
        except Exception as e:
            print(f"   ℹ️  Index check not available: {e}")
            
    def auto_repair_issues(self):
        """Attempt to auto-repair found issues"""
        repairs = 0
        
        for issue in self.issues_found:
            try:
                if issue['type'] == 'missing_category':
                    repairs += self._repair_missing_categories(issue)
                elif issue['type'] == 'orphaned_bom_components':
                    repairs += self._repair_orphaned_bom_components(issue)
                elif issue['type'] == 'empty_boms':
                    repairs += self._repair_empty_boms(issue)
                elif issue['type'] == 'missing_boms':
                    repairs += self._repair_missing_boms(issue)
                elif issue['type'] == 'negative_inventory':
                    repairs += self._repair_negative_inventory(issue)
                elif issue['type'] == 'over_allocated':
                    repairs += self._repair_over_allocated(issue)
                elif issue['type'] == 'orphaned_inventory':
                    repairs += self._repair_orphaned_inventory(issue)
                elif issue['type'] == 'missing_uom':
                    repairs += self._repair_missing_uom(issue)
                elif issue['type'] == 'zero_cost_products':
                    repairs += self._repair_zero_cost_products(issue)
                elif issue['type'] == 'stale_planned_orders':
                    repairs += self._repair_stale_planned_orders(issue)
                    
            except Exception as e:
                print(f"   ❌ Error repairing {issue['type']}: {e}")
                
        print(f"   ✅ {repairs} issues repaired")
        
    def _repair_missing_categories(self, issue):
        """Create default category and assign to products"""
        # Create default category
        default_category = self.db.query(ItemCategory).filter(
            ItemCategory.name == "Uncategorized"
        ).first()
        
        if not default_category:
            default_category = ItemCategory(
                name="Uncategorized",
                description="Auto-created for products without categories",
                created_by="system"
            )
            self.db.add(default_category)
            self.db.flush()
        
        # Assign products to default category
        for product in issue['products']:
            product.category_id = default_category.id
        
        self.db.commit()
        return issue['count']
        
    def _repair_orphaned_bom_components(self, issue):
        """Remove BOM lines referencing non-existent products"""
        for bom_line in issue['bom_lines']:
            self.db.delete(bom_line)
        
        self.db.commit()
        return issue['count']
        
    def _repair_empty_boms(self, issue):
        """Deactivate BOMs with no lines"""
        for bom in issue['boms']:
            bom.active = False
            
        self.db.commit()
        return issue['count']
        
    def _repair_missing_boms(self, issue):
        """Set has_bom=False for products without BOMs"""
        for product in issue['products']:
            product.has_bom = False
            
        self.db.commit()
        return issue['count']
        
    def _repair_negative_inventory(self, issue):
        """Zero out negative inventory"""
        for inventory in issue['records']:
            inventory.on_hand_quantity = Decimal('0')
            inventory.allocated_quantity = Decimal('0')
            
        self.db.commit()
        return issue['count']
        
    def _repair_over_allocated(self, issue):
        """Fix over-allocated inventory"""
        for inventory in issue['records']:
            inventory.allocated_quantity = inventory.on_hand_quantity
            
        self.db.commit()
        return issue['count']
        
    def _repair_orphaned_inventory(self, issue):
        """Remove inventory for non-existent products"""
        for inventory in issue['records']:
            self.db.delete(inventory)
            
        self.db.commit()
        return issue['count']
        
    def _repair_missing_uom(self, issue):
        """Set default UOM for products"""
        for product in issue['products']:
            # Assign sensible defaults based on item type
            if product.item_type in ['raw_material', 'component']:
                product.unit = 'EA'  # Default to each
            elif 'filament' in (product.name or '').lower():
                product.unit = 'KG'  # Filament typically measured in weight
            else:
                product.unit = 'EA'
                
        self.db.commit()
        return issue['count']
        
    def _repair_zero_cost_products(self, issue):
        """Set minimum cost for products"""
        for product in issue['products']:
            product.standard_cost = Decimal('0.01')  # Minimum $0.01
            
        self.db.commit()
        return issue['count']
        
    def _repair_stale_planned_orders(self, issue):
        """Remove planned orders for non-existent products"""
        for order in issue['orders']:
            self.db.delete(order)
            
        self.db.commit()
        return issue['count']
        
    def print_summary(self):
        """Print final summary"""
        print("\n" + "=" * 50)
        if not self.issues_found:
            print("🎉 DATABASE INTEGRITY: EXCELLENT")
            print("   No issues found. Database is healthy!")
        else:
            print(f"⚠️  DATABASE INTEGRITY: {len(self.issues_found)} ISSUES FOUND")
            if self.repairs_made:
                print(f"✅ {len(self.repairs_made)} issues were auto-repaired")
                
        print("\n📋 Recommendations:")
        print("   • Run this check weekly during development")
        print("   • Run before major MRP calculations")  
        print("   • Monitor inventory allocation vs on-hand")
        print("   • Keep BOMs clean and up-to-date")
        
        if len(self.issues_found) > 5:
            print("   • Consider data cleanup procedures")
            print("   • Review data entry processes")
            
        print("\n🔧 Next Steps:")
        print("   • Test MRP calculation: `python test_order_status.py`")
        print("   • Create test data: `python scripts/seed_production_test_data.py`")
        print("   • Run E2E tests: `npm run test:e2e` (from frontend/)")
        
    def __del__(self):
        """Clean up database connection"""
        if hasattr(self, 'db'):
            self.db.close()

def main():
    """Run database integrity check"""
    checker = DatabaseIntegrityChecker()
    
    try:
        # Check if --no-repair flag was passed
        auto_repair = '--no-repair' not in sys.argv
        
        checker.run_full_check(auto_repair=auto_repair)
        
    except Exception as e:
        print(f"\n❌ Error during integrity check: {e}")
        import traceback
        traceback.print_exc()
    finally:
        checker.db.close()

if __name__ == "__main__":
    main()
