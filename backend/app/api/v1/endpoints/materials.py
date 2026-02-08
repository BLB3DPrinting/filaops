"""
Material API Endpoints

Provides material type and color options for the quote portal.
Uses material_service for business logic (ARCHITECT-003).
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import io

from app.db.session import get_db
from app.models.user import User
from app.api.v1.deps import get_current_user
from app.models.inventory import Inventory
from app.logging_config import get_logger
from app.services.material_service import (
    get_portal_material_options,
    get_available_material_types,
    get_available_colors_for_material,
    get_material_product_for_bom,
    create_color_for_material,
    import_materials_from_csv,
    MaterialNotFoundError,
)

logger = get_logger(__name__)

router = APIRouter()


# ============================================================================
# SCHEMAS
# ============================================================================

class ColorOption(BaseModel):
    """Color option for dropdown"""
    code: str
    name: str
    hex: str | None
    hex_secondary: str | None = None
    in_stock: bool = True
    quantity_kg: float = 0.0


class MaterialTypeOption(BaseModel):
    """Material type with available colors"""
    code: str
    name: str
    description: str | None
    base_material: str
    price_multiplier: float
    strength_rating: int | None
    requires_enclosure: bool
    colors: List[ColorOption]


class MaterialOptionsResponse(BaseModel):
    """Response containing all material options for portal"""
    materials: List[MaterialTypeOption]


class SimpleColorOption(BaseModel):
    """Simple color option"""
    code: str
    name: str
    hex: str | None


class ColorsResponse(BaseModel):
    """Response containing colors for a material type"""
    material_type: str
    colors: List[SimpleColorOption]


class ColorCreate(BaseModel):
    """Schema for creating a new color"""
    name: str
    code: str | None = None
    hex_code: str | None = None


class ColorCreateResponse(BaseModel):
    """Response after creating a color"""
    id: int
    code: str
    name: str
    hex_code: str | None
    material_type_code: str
    message: str


class MaterialCSVImportResult(BaseModel):
    """Result of material CSV import"""
    total_rows: int
    created: int
    updated: int
    skipped: int
    errors: List[dict]


class MaterialTypeItem(BaseModel):
    """A single material type entry for the types list"""
    code: str
    name: str
    base_material: str
    description: str | None
    price_multiplier: float
    strength_rating: int | None
    requires_enclosure: bool


class MaterialTypesResponse(BaseModel):
    """Response for GET /types — list of material type options"""
    materials: List[MaterialTypeItem]


class BOMItemEntry(BaseModel):
    """A single material entry formatted for BOM selection"""
    id: int
    sku: str
    name: str
    description: str
    item_type: str
    procurement_type: str
    unit: str
    standard_cost: float
    in_stock: bool
    quantity_available: float
    material_code: str
    color_code: str
    color_hex: str | None


class MaterialsForBOMResponse(BaseModel):
    """Response for GET /for-bom — materials formatted for BOM selection"""
    items: List[BOMItemEntry]


class MaterialPricingResponse(BaseModel):
    """Response for GET /pricing/{material_type_code} — pricing info"""
    code: str
    name: str
    base_material: str
    density: float
    base_price_per_kg: float
    price_multiplier: float
    volumetric_flow_limit: float | None
    nozzle_temp_min: int | None
    nozzle_temp_max: int | None
    bed_temp_min: int | None
    bed_temp_max: int | None
    requires_enclosure: bool


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/options", response_model=MaterialOptionsResponse)
def get_material_options(
    in_stock_only: bool = True,
    db: Session = Depends(get_db),
):
    """Get all material options for the quote portal."""
    try:
        materials = get_portal_material_options(db)

        return MaterialOptionsResponse(
            materials=[
                MaterialTypeOption(
                    code=m["code"],
                    name=m["name"],
                    description=m.get("description"),
                    base_material=m["base_material"],
                    price_multiplier=m["price_multiplier"],
                    strength_rating=m.get("strength_rating"),
                    requires_enclosure=m.get("requires_enclosure", False),
                    colors=[
                        ColorOption(
                            code=c["code"],
                            name=c["name"],
                            hex=c.get("hex"),
                            hex_secondary=c.get("hex_secondary"),
                            in_stock=c.get("in_stock", True),
                            quantity_kg=c.get("quantity_kg", 0.0),
                        )
                        for c in m["colors"]
                    ],
                )
                for m in materials
            ]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types", response_model=MaterialTypesResponse)
def list_material_types(
    customer_visible_only: bool = True,
    db: Session = Depends(get_db),
) -> MaterialTypesResponse:
    """Get list of material types (for first dropdown)."""
    try:
        materials = get_available_material_types(
            db, customer_visible_only=customer_visible_only
        )

        return {
            "materials": [
                {
                    "code": m.code,
                    "name": m.name,
                    "base_material": m.base_material,
                    "description": m.description,
                    "price_multiplier": float(m.price_multiplier),
                    "strength_rating": m.strength_rating,
                    "requires_enclosure": m.requires_enclosure,
                }
                for m in materials
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types/{material_type_code}/colors", response_model=ColorsResponse)
def list_colors_for_material(
    material_type_code: str,
    in_stock_only: bool = True,
    customer_visible_only: bool = True,
    db: Session = Depends(get_db),
):
    """Get available colors for a specific material type (for second dropdown)."""
    try:
        colors = get_available_colors_for_material(
            db,
            material_type_code=material_type_code,
            in_stock_only=in_stock_only,
            customer_visible_only=customer_visible_only,
        )

        return ColorsResponse(
            material_type=material_type_code,
            colors=[
                SimpleColorOption(code=c.code, name=c.name, hex=c.hex_code)
                for c in colors
            ],
        )
    except MaterialNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Material type not found: {material_type_code}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/types/{material_type_code}/colors", response_model=ColorCreateResponse)
def create_color_for_material_endpoint(
    material_type_code: str,
    color_data: ColorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new color and link it to a material type."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Admin access required to create colors"
        )

    color, material_type = create_color_for_material(
        db,
        material_type_code,
        name=color_data.name,
        code=color_data.code,
        hex_code=color_data.hex_code,
    )

    return ColorCreateResponse(
        id=color.id,
        code=color.code,
        name=color.name,
        hex_code=color.hex_code,
        material_type_code=material_type_code,
        message=f"Color '{color.name}' created and linked to {material_type.name}",
    )


@router.get("/for-bom", response_model=MaterialsForBOMResponse)
def get_materials_for_bom(db: Session = Depends(get_db)) -> MaterialsForBOMResponse:
    """Get all materials formatted for BOM usage."""
    try:
        materials = get_available_material_types(db, customer_visible_only=False)
        result = []

        for material in materials:
            colors = get_available_colors_for_material(
                db, material.code, in_stock_only=False, customer_visible_only=False,
            )

            for color in colors:
                try:
                    product, _ = get_material_product_for_bom(
                        db,
                        material_type_code=material.code,
                        color_code=color.code,
                        require_in_stock=False,
                    )

                    inventory = db.query(Inventory).filter(
                        Inventory.product_id == product.id
                    ).first()

                    quantity_available = 0.0
                    in_stock = False
                    if inventory:
                        quantity_available = float(inventory.on_hand_quantity or 0)
                        in_stock = quantity_available > 0

                    result.append({
                        "id": product.id,
                        "sku": product.sku,
                        "name": f"{material.name} - {color.name}",
                        "description": material.description or f"{material.base_material} filament",
                        "item_type": "supply",
                        "procurement_type": "buy",
                        "unit": "kg",
                        "standard_cost": (
                            float(product.standard_cost) if product.standard_cost
                            else float(material.base_price_per_kg)
                        ),
                        "in_stock": in_stock,
                        "quantity_available": quantity_available,
                        "material_code": material.code,
                        "color_code": color.code,
                        "color_hex": color.hex_code,
                    })
                except Exception as e:
                    logger.warning(
                        f"Failed to process material {material.code}/{color.code}: {e}"
                    )
                    continue

        return {"items": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pricing/{material_type_code}", response_model=MaterialPricingResponse)
def get_material_pricing(
    material_type_code: str,
    db: Session = Depends(get_db),
) -> MaterialPricingResponse:
    """Get pricing information for a material type."""
    try:
        materials = get_available_material_types(db, customer_visible_only=False)
        material = next((m for m in materials if m.code == material_type_code), None)

        if not material:
            raise HTTPException(
                status_code=404, detail=f"Material type not found: {material_type_code}"
            )

        return {
            "code": material.code,
            "name": material.name,
            "base_material": material.base_material,
            "density": float(material.density),
            "base_price_per_kg": float(material.base_price_per_kg),
            "price_multiplier": float(material.price_multiplier),
            "volumetric_flow_limit": (
                float(material.volumetric_flow_limit) if material.volumetric_flow_limit else None
            ),
            "nozzle_temp_min": material.nozzle_temp_min,
            "nozzle_temp_max": material.nozzle_temp_max,
            "bed_temp_min": material.bed_temp_min,
            "bed_temp_max": material.bed_temp_max,
            "requires_enclosure": material.requires_enclosure,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CSV IMPORT
# ============================================================================

@router.get("/import/template")
async def download_material_import_template():
    """Download CSV template for material inventory import."""
    template = """Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)
PLA Matte,MAT-FDM-PLA-MATTE-CHAR,PLA Matte Charcoal,PLA_MATTE,Charcoal,#0C0C0C,kg,Active,19.99,0
PLA Basic,MAT-FDM-PLA-BASIC-RED,PLA Basic Red,PLA_BASIC,Red,#FF0000,kg,Active,19.99,0
PLA Silk,MAT-FDM-PLA-SILK-GOLD,PLA Silk Gold,PLA_SILK,Gold,#F4A925,kg,Active,22.99,0"""

    return StreamingResponse(
        io.BytesIO(template.encode("utf-8")),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=material_inventory_template.csv"
        },
    )


@router.post("/import", response_model=MaterialCSVImportResult)
async def import_materials_csv_endpoint(
    file: UploadFile = File(...),
    update_existing: bool = Query(False, description="Update existing materials if SKU exists"),
    import_categories: bool = Query(True, description="Import categories from CSV and nest under Filament"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import material inventory from CSV file."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()

    result = import_materials_from_csv(
        db,
        file_content=content,
        update_existing=update_existing,
        import_categories=import_categories,
    )

    return MaterialCSVImportResult(**result)
