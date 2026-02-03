"""
Products API Endpoints

Uses product_service for business logic (ARCHITECT-003).
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.product import Product
from app.models.user import User
from app.logging_config import get_logger
from app.api.v1.deps import get_current_user
from app.services.operation_generation import get_product_routing_details
from app.services import product_service
from app.schemas.routing_operations import (
    ProductRoutingResponse,
    RoutingOperationInfo,
)

router = APIRouter()
logger = get_logger(__name__)


class ProductCreate(BaseModel):
    """Create product request"""
    sku: str
    name: str
    description: Optional[str] = None
    category_id: Optional[int] = None
    unit: str = "EA"
    standard_cost: Optional[float] = None
    selling_price: Optional[float] = None
    is_raw_material: bool = False
    active: bool = True
    image_url: Optional[str] = None


class ProductUpdate(BaseModel):
    """Update product request"""
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    unit: Optional[str] = None
    standard_cost: Optional[float] = None
    selling_price: Optional[float] = None
    is_raw_material: Optional[bool] = None
    active: Optional[bool] = None
    image_url: Optional[str] = None


class ProductResponse(BaseModel):
    """Product response"""
    id: int
    sku: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit: str
    cost: Optional[float] = None
    selling_price: Optional[float] = None
    weight: Optional[float] = None
    is_raw_material: bool
    has_bom: bool
    active: bool
    woocommerce_product_id: Optional[int] = None
    image_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ProductListResponse(BaseModel):
    """Product list response"""
    total: int
    items: List[ProductResponse]

@router.get("", response_model=ProductListResponse)
async def list_products(
    category: Optional[str] = None,
    active_only: bool = True,
    search: Optional[str] = None,
    has_bom: Optional[bool] = None,
    procurement_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List products with optional filtering

    - **category**: Filter by category (e.g., 'Finished Goods', 'Raw Materials')
    - **active_only**: Only show active products (default: True)
    - **search**: Search by SKU or name
    - **has_bom**: Filter by whether product has a BOM (True/False)
    - **procurement_type**: Filter by procurement type ('make', 'buy', 'make_or_buy')
    - **limit**: Max results (default: 50)
    - **offset**: Pagination offset (default: 0)
    """
    try:
        products, total = product_service.list_products(
            db,
            category=category,
            active_only=active_only,
            search=search,
            has_bom=has_bom,
            procurement_type=procurement_type,
            limit=limit,
            offset=offset,
        )

        return ProductListResponse(
            total=total,
            items=[ProductResponse.from_orm(p) for p in products]
        )

    except Exception as e:
        logger.error(f"Failed to list products: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{id}", response_model=ProductResponse)
async def get_product(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific product by ID"""
    product = product_service.get_product(db, id)
    return ProductResponse.from_orm(product)

@router.get("/sku/{sku}", response_model=ProductResponse)
async def get_product_by_sku(
    sku: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific product by SKU"""
    product = product_service.get_product_by_sku(db, sku)
    return ProductResponse.from_orm(product)


@router.post("", response_model=ProductResponse)
async def create_product(
    request: ProductCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new product"""
    try:
        product = product_service.create_product(db, data=request.model_dump())
        return ProductResponse.from_orm(product)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create product: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{id}", response_model=ProductResponse)
async def update_product(
    id: int,
    request: ProductUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing product"""
    try:
        product = product_service.update_product(
            db, id, data=request.model_dump(exclude_unset=True)
        )
        return ProductResponse.from_orm(product)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update product: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Product Routing Endpoint (API-404)
# =============================================================================


@router.get(
    "/{product_id}/routing",
    response_model=ProductRoutingResponse,
    summary="Get routing for a product"
)
def get_product_routing(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get routing details for a product."""
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    routing_info = get_product_routing_details(db, product_id)

    if not routing_info:
        return ProductRoutingResponse(
            product_id=product_id,
            routing_id=None,
            operations=[]
        )

    return ProductRoutingResponse(
        product_id=product_id,
        routing_id=routing_info['routing_id'],
        routing_code=routing_info['routing_code'],
        routing_name=routing_info['routing_name'],
        is_active=routing_info['is_active'],
        operations=[
            RoutingOperationInfo(**op) for op in routing_info['operations']
        ]
    )
