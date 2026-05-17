"""
Pydantic schemas for customer quote system

Request and response models for quote creation, file uploads, and workflow
"""
from typing import Optional, List
from datetime import datetime, timezone, date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator


class QuoteFileUpload(BaseModel):
    """Schema for file upload metadata (internal use)"""
    original_filename: str
    stored_filename: str
    file_path: str
    file_size_bytes: int
    file_format: str
    file_hash: str
    mime_type: str


class QuoteFileResponse(BaseModel):
    """Schema for quote file data response"""
    id: int
    quote_id: int
    original_filename: str
    file_size_bytes: int
    file_format: str
    is_valid: bool
    validation_errors: Optional[str] = None
    processed: bool
    processing_error: Optional[str] = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}

    @property
    def file_size_mb(self) -> float:
        """Get file size in megabytes"""
        return self.file_size_bytes / (1024 * 1024)


class QuoteCreate(BaseModel):
    """Schema for creating a new quote request"""
    product_name: Optional[str] = Field(None, max_length=255, description="Customer-provided product name")
    quantity: int = Field(1, ge=1, le=1000, description="Number of units to print")
    material_type: str = Field(..., max_length=50, description="Material: PLA, PETG, ABS, ASA, TPU")
    finish: str = Field("standard", max_length=50, description="Finish: standard, smooth, painted")
    rush_level: str = Field("standard", max_length=20, description="Rush level: standard, rush, super_rush, urgent")
    requested_delivery_date: Optional[date] = Field(None, description="Customer requested delivery date")
    customer_notes: Optional[str] = Field(None, max_length=1000, description="Special requests or notes")

    @field_validator('material_type')
    @classmethod
    def validate_material_type(cls, v: str) -> str:
        """Validate material type is supported"""
        allowed_materials = ['PLA', 'PETG', 'ABS', 'ASA', 'TPU']
        v_upper = v.upper()
        if v_upper not in allowed_materials:
            raise ValueError(f"Invalid material type. Allowed: {', '.join(allowed_materials)}")
        return v_upper

    @field_validator('finish')
    @classmethod
    def validate_finish(cls, v: str) -> str:
        """Validate finish type is supported"""
        allowed_finishes = ['standard', 'smooth', 'painted']
        v_lower = v.lower()
        if v_lower not in allowed_finishes:
            raise ValueError(f"Invalid finish type. Allowed: {', '.join(allowed_finishes)}")
        return v_lower

    @field_validator('rush_level')
    @classmethod
    def validate_rush_level(cls, v: str) -> str:
        """Validate rush level is supported"""
        allowed_rush = ['standard', 'rush', 'super_rush', 'urgent']
        v_lower = v.lower()
        if v_lower not in allowed_rush:
            raise ValueError(f"Invalid rush level. Allowed: {', '.join(allowed_rush)}")
        return v_lower


class QuoteResponse(BaseModel):
    """Schema for quote data response"""
    id: int
    user_id: int
    quote_number: str

    # Product Details
    product_name: Optional[str] = None
    quantity: int
    material_type: str
    finish: str

    # Pricing
    material_grams: Optional[Decimal] = None
    print_time_hours: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    total_price: Decimal
    margin_percent: Optional[Decimal] = None

    # File Metadata
    file_format: str
    file_size_bytes: int
    dimensions_x: Optional[Decimal] = None
    dimensions_y: Optional[Decimal] = None
    dimensions_z: Optional[Decimal] = None

    # Workflow Status
    status: str
    approval_method: Optional[str] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

    # Auto-Approval
    auto_approved: bool
    auto_approve_eligible: bool
    requires_review_reason: Optional[str] = None

    # Rush Order
    rush_level: str
    requested_delivery_date: Optional[date] = None

    # Notes
    customer_notes: Optional[str] = None
    admin_notes: Optional[str] = None

    # Conversion
    sales_order_id: Optional[int] = None
    converted_at: Optional[datetime] = None

    # Auto-created product
    product_id: Optional[int] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    # Optional defensively: legacy rows created before the server_default
    # migration may have NULL expires_at. The migration backfills them,
    # but keeping this Optional means a single stray NULL can never again
    # 500 the entire list endpoint via response validation.
    expires_at: Optional[datetime] = None

    # Related data
    files: List[QuoteFileResponse] = []

    model_config = {"from_attributes": True}

    @property
    def is_expired(self) -> bool:
        """Check if quote has expired"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires = self.expires_at.replace(tzinfo=None) if self.expires_at and self.expires_at.tzinfo else self.expires_at
        return now > expires

    @property
    def file_size_mb(self) -> float:
        """Get primary file size in megabytes"""
        return self.file_size_bytes / (1024 * 1024)


class QuoteListResponse(BaseModel):
    """Schema for quote list item (minimal data for listing)"""
    id: int
    quote_number: str
    product_name: Optional[str] = None
    quantity: int
    material_type: str
    color: Optional[str] = None
    total_price: Decimal
    status: str
    auto_approved: bool
    rush_level: str
    created_at: datetime
    # See QuoteResponse.expires_at for rationale on Optional.
    expires_at: Optional[datetime] = None
    # For navigation
    product_id: Optional[int] = None
    sales_order_id: Optional[int] = None

    model_config = {"from_attributes": True}

    @property
    def is_expired(self) -> bool:
        """Check if quote has expired"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires = self.expires_at.replace(tzinfo=None) if self.expires_at and self.expires_at.tzinfo else self.expires_at
        return now > expires


class QuoteUpdateStatus(BaseModel):
    """Schema for updating quote status (admin only)"""
    status: str = Field(..., description="New status: approved, rejected, cancelled")
    rejection_reason: Optional[str] = Field(None, max_length=500, description="Reason for rejection")
    admin_notes: Optional[str] = Field(None, max_length=1000, description="Internal admin notes")

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status transition is allowed"""
        allowed_statuses = ['approved', 'rejected', 'cancelled']
        v_lower = v.lower()
        if v_lower not in allowed_statuses:
            raise ValueError(f"Invalid status. Allowed for manual update: {', '.join(allowed_statuses)}")
        return v_lower


class QuoteAccept(BaseModel):
    """Schema for customer accepting a quote"""
    accepted: bool = Field(True, description="Customer acceptance confirmation")
    customer_notes: Optional[str] = Field(None, max_length=1000, description="Additional notes from customer")


class QuotePricingResponse(BaseModel):
    """Schema for Bambu Suite pricing response"""
    material_grams: Decimal
    print_time_hours: Decimal
    unit_price: Decimal
    total_price: Decimal
    margin_percent: Decimal
    dimensions_x: Decimal
    dimensions_y: Decimal
    dimensions_z: Decimal
    auto_approve_eligible: bool
    requires_review_reason: Optional[str] = None


class QuoteStatsResponse(BaseModel):
    """Schema for quote statistics (admin dashboard)"""
    total_quotes: int
    pending_quotes: int
    approved_quotes: int
    rejected_quotes: int
    expired_quotes: int
    converted_quotes: int
    auto_approved_count: int
    manual_approved_count: int
    total_value: Decimal
    average_quote_value: Decimal


class BambuQuoteRequest(BaseModel):
    """Schema for quote request to Bambu Suite API"""
    file_path: str
    material_type: str
    quantity: int
    finish: str = "standard"
    rush_level: str = "standard"


class BambuQuoteResponse(BaseModel):
    """Schema for quote response from Bambu Suite API"""
    success: bool
    material_grams: Optional[Decimal] = None
    print_time_hours: Optional[Decimal] = None
    material_cost: Optional[Decimal] = None
    labor_cost: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    total_price: Optional[Decimal] = None
    dimensions_x: Optional[Decimal] = None
    dimensions_y: Optional[Decimal] = None
    dimensions_z: Optional[Decimal] = None
    error: Optional[str] = None
    error_code: Optional[str] = None


# ============================================================================
# PORTAL QUOTE SCHEMAS (Public/Anonymous)
# ============================================================================

class QuoteMaterialCreate(BaseModel):
    """Schema for per-filament material breakdown (multi-material quotes)"""
    slot_number: int = Field(..., ge=1, le=16, description="AMS slot number (1-indexed)")
    material_type: str = Field(..., max_length=50, description="Material type code: PLA_BASIC, PETG_HF, etc.")
    color_code: Optional[str] = Field(None, max_length=30, description="Color code: BLK, WHT, etc.")
    color_name: Optional[str] = Field(None, max_length=100, description="Display color name")
    color_hex: Optional[str] = Field(None, max_length=7, description="Hex color code: #FFFFFF")
    material_grams: Decimal = Field(..., ge=0, description="Material weight in grams for this slot")
    is_primary: bool = Field(False, description="Whether this is the primary/main color")


class MultiMaterialData(BaseModel):
    """Schema for multi-material quote data from slicer"""
    is_multi_material: bool = Field(False, description="Whether this is a multi-material print")
    material_count: int = Field(1, ge=1, description="Number of materials/colors used")
    filament_types: Optional[List[str]] = Field(None, description="List of material types per slot")
    filament_weights_grams: Optional[List[float]] = Field(None, description="List of weights per slot in grams")
    filament_colors: Optional[List[str]] = Field(None, description="List of color codes per slot")
    filament_color_names: Optional[List[str]] = Field(None, description="List of color names per slot")
    filament_color_hexes: Optional[List[str]] = Field(None, description="List of hex colors per slot")
    tool_change_count: Optional[int] = Field(None, description="Number of tool changes")


class PortalQuoteCreate(BaseModel):
    """Schema for creating a quote from the public portal (no auth required)"""
    # File info
    filename: str = Field(..., max_length=255, description="Original filename")
    file_format: str = Field(..., max_length=10, description="File extension: .3mf or .stl")
    
    # Quote details
    material: str = Field(..., max_length=50, description="Material: PLA, PETG, ABS, ASA, TPU")
    quality: str = Field("standard", max_length=50, description="Quality level")
    infill: Optional[str] = Field("standard", max_length=20, description="Infill/strength level")
    color: Optional[str] = Field(None, max_length=50, description="Selected color code")
    color_name: Optional[str] = Field(None, max_length=100, description="Selected color display name")
    quantity: int = Field(1, ge=1, le=1000, description="Number of units")
    
    # Pricing from Print Suite
    unit_price: Decimal = Field(..., description="Price per unit")
    total_price: Decimal = Field(..., description="Total price (unit_price * quantity)")
    material_grams: Decimal = Field(..., description="Material weight in grams")
    print_time_minutes: Decimal = Field(..., description="Print time in minutes")
    
    # Dimensions
    dimensions_x: Optional[Decimal] = Field(None, description="X dimension in mm")
    dimensions_y: Optional[Decimal] = Field(None, description="Y dimension in mm")
    dimensions_z: Optional[Decimal] = Field(None, description="Z dimension in mm")
    
    # Stock status
    material_in_stock: Optional[bool] = Field(True, description="Whether material/color is in stock")
    
    # Customer info
    customer_id: Optional[int] = Field(None, description="Logged-in customer ID")
    customer_email: Optional[str] = Field(None, max_length=255, description="Customer email for follow-up")
    customer_notes: Optional[str] = Field(None, max_length=1000, description="Special requests")

    # Multi-material data (from slicer output)
    multi_material: Optional[MultiMaterialData] = Field(None, description="Multi-material/multi-color breakdown from slicer")

    @field_validator('material')
    @classmethod
    def validate_material(cls, v: str) -> str:
        # Accept base materials and specific variants
        base_materials = ['PLA', 'PETG', 'ABS', 'ASA', 'TPU']
        v_upper = v.upper()

        # Check if it's a base material
        if v_upper in base_materials:
            return v_upper

        # Check if it's a variant (e.g., PLA_BASIC, PLA_SILK, PETG_HF)
        base = v_upper.split('_')[0]
        if base in base_materials:
            return v_upper

        raise ValueError(f"Invalid material. Must be one of {', '.join(base_materials)} or a variant")


class PortalQuoteResponse(BaseModel):
    """Response for portal quote creation"""
    id: int
    quote_number: str
    filename: str
    material: str
    quality: str
    infill: Optional[str] = None
    color: Optional[str] = None
    color_name: Optional[str] = None
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    material_grams: Decimal
    print_time_minutes: Decimal
    material_in_stock: Optional[bool] = True
    status: str
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class MultiColorSlot(BaseModel):
    """Color selection for a single slot in multi-color print"""
    slot: int
    color_code: str
    color_name: Optional[str] = None
    color_hex: Optional[str] = None
    is_primary: Optional[bool] = False


class MultiColorInfo(BaseModel):
    """Multi-color print configuration"""
    primary_slot: Optional[int] = Field(None, description="1-indexed slot number for the primary/main color")
    slot_colors: List[MultiColorSlot]


class PortalAcceptQuote(BaseModel):
    """Schema for customer accepting a quote with shipping info"""
    # Shipping address fields
    shipping_name: Optional[str] = Field(None, max_length=200)
    shipping_address_line1: str = Field(..., max_length=255)
    shipping_address_line2: Optional[str] = Field(None, max_length=255)
    shipping_city: str = Field(..., max_length=100)
    shipping_state: str = Field(..., max_length=50)
    shipping_zip: str = Field(..., max_length=20)
    shipping_country: str = Field("USA", max_length=100)
    shipping_phone: Optional[str] = Field(None, max_length=30)
    # Shipping selection (from EasyPost)
    shipping_rate_id: Optional[str] = Field(None, max_length=100)
    shipping_carrier: Optional[str] = Field(None, max_length=50)
    shipping_service: Optional[str] = Field(None, max_length=100)
    shipping_cost: Optional[float] = None
    # Multi-color print options
    print_mode: Optional[str] = Field(None, description="'single' or 'multi' for multi-material prints")
    adjusted_unit_price: Optional[float] = Field(None, description="Adjusted price if customer chose single-color")
    multi_color_info: Optional[MultiColorInfo] = Field(None, description="Color selections for multi-color prints")


class PortalSubmitForReview(BaseModel):
    """Schema for submitting a quote for engineer review"""
    # Customer contact (required for follow-up)
    customer_email: str = Field(..., max_length=255, description="Customer email for payment link")
    customer_name: Optional[str] = Field(None, max_length=200, description="Customer name")
    # Shipping address fields
    shipping_name: Optional[str] = Field(None, max_length=200)
    shipping_address_line1: str = Field(..., max_length=255)
    shipping_address_line2: Optional[str] = Field(None, max_length=255)
    shipping_city: str = Field(..., max_length=100)
    shipping_state: str = Field(..., max_length=50)
    shipping_zip: str = Field(..., max_length=20)
    shipping_country: str = Field("USA", max_length=100)
    shipping_phone: Optional[str] = Field(None, max_length=30)
    # Shipping selection (from EasyPost)
    shipping_rate_id: Optional[str] = Field(None, max_length=100)
    shipping_carrier: Optional[str] = Field(None, max_length=50)
    shipping_service: Optional[str] = Field(None, max_length=100)
    shipping_cost: Optional[float] = None
