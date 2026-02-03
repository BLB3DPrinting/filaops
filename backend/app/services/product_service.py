"""
Product Service — CRUD and validation for products.

Extracted from products.py (ARCHITECT-003).
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.product import Product
from app.core.utils import get_or_404, check_unique_or_400

logger = get_logger(__name__)


def product_has_transactions(db: Session, product_id: int) -> tuple[bool, str]:
    """
    Check if a product has transactional history that would prevent SKU changes.

    Returns:
        (has_transactions, reason)
    """
    from app.models.purchase_order import PurchaseOrderLine
    from app.models.inventory import InventoryTransaction
    from app.models.traceability import MaterialLot

    po_lines = (
        db.query(PurchaseOrderLine)
        .filter(PurchaseOrderLine.product_id == product_id)
        .count()
    )
    if po_lines > 0:
        return True, f"Product has {po_lines} purchase order line(s)"

    inv_txns = (
        db.query(InventoryTransaction)
        .filter(InventoryTransaction.product_id == product_id)
        .count()
    )
    if inv_txns > 0:
        return True, f"Product has {inv_txns} inventory transaction(s)"

    lots = (
        db.query(MaterialLot)
        .filter(MaterialLot.product_id == product_id)
        .count()
    )
    if lots > 0:
        return True, f"Product has {lots} material lot(s)"

    return False, ""


def list_products(
    db: Session,
    *,
    category: str | None = None,
    active_only: bool = True,
    search: str | None = None,
    has_bom: bool | None = None,
    procurement_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Product], int]:
    """
    List products with filtering and pagination.

    Returns:
        (products, total_count)
    """
    query = db.query(Product)

    if active_only:
        query = query.filter(Product.active.is_(True))

    if category:
        from app.models.item_category import ItemCategory

        query = query.join(ItemCategory, Product.category_id == ItemCategory.id).filter(
            ItemCategory.name.ilike(f"%{category}%")
        )

    if has_bom is not None:
        query = query.filter(Product.has_bom == has_bom)

    if procurement_type:
        query = query.filter(Product.procurement_type == procurement_type)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (Product.sku.ilike(search_pattern)) | (Product.name.ilike(search_pattern))
        )

    total = query.count()
    products = query.order_by(Product.id).offset(offset).limit(limit).all()

    return products, total


def get_product(db: Session, product_id: int) -> Product:
    """Get product by ID or raise 404."""
    return get_or_404(db, Product, product_id)


def get_product_by_sku(db: Session, sku: str) -> Product:
    """Get product by SKU or raise 404."""
    product = db.query(Product).filter(Product.sku == sku).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product with SKU {sku} not found")
    return product


def create_product(db: Session, *, data: dict) -> Product:
    """Create a new product."""
    check_unique_or_400(db, Product, "sku", data["sku"])

    product = Product(**data)
    db.add(product)
    db.commit()
    db.refresh(product)

    logger.info(f"Created product: {product.sku}")
    return product


def update_product(db: Session, product_id: int, *, data: dict) -> Product:
    """
    Update a product.

    Args:
        db: Database session
        product_id: Product ID
        data: Fields to update (from ProductUpdate schema model_dump(exclude_unset=True))
    """
    product = get_or_404(db, Product, product_id)

    if "sku" in data and data["sku"] != product.sku:
        has_txns, reason = product_has_transactions(db, product_id)
        if has_txns:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot change SKU: {reason}. Create a new product instead.",
            )
        check_unique_or_400(db, Product, "sku", data["sku"])

    for field, value in data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    logger.info(f"Updated product: {product.sku}")
    return product
