"""
Unit of Measure (UOM) Service

Provides conversion functions between compatible units of measure.
"""
from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.uom import UnitOfMeasure


# Maximum decimal places for quantity formatting
# This prevents excessively long strings while maintaining precision for UOM conversions
MAX_DECIMAL_PLACES = 10


# ============================================================================
# Inline UOM Conversion (fallback when database UOM table is empty)
# ============================================================================

INLINE_UOM_CONVERSIONS = {
    # Mass conversions (to KG)
    'G': {'base': 'KG', 'factor': Decimal('0.001')},
    'KG': {'base': 'KG', 'factor': Decimal('1')},
    'LB': {'base': 'KG', 'factor': Decimal('0.453592')},
    'OZ': {'base': 'KG', 'factor': Decimal('0.0283495')},
    # Length conversions (to M)
    'MM': {'base': 'M', 'factor': Decimal('0.001')},
    'CM': {'base': 'M', 'factor': Decimal('0.01')},
    'M': {'base': 'M', 'factor': Decimal('1')},
    'IN': {'base': 'M', 'factor': Decimal('0.0254')},
    'FT': {'base': 'M', 'factor': Decimal('0.3048')},
    # Volume conversions (to L)
    'ML': {'base': 'L', 'factor': Decimal('0.001')},
    'L': {'base': 'L', 'factor': Decimal('1')},
    # Count units (no conversion)
    'EA': {'base': 'EA', 'factor': Decimal('1')},
    'PK': {'base': 'PK', 'factor': Decimal('1')},
    'BOX': {'base': 'BOX', 'factor': Decimal('1')},
    'ROLL': {'base': 'ROLL', 'factor': Decimal('1')},
}

# ============================================================================
# CRITICAL: Cost Conversion Logic - DO NOT MODIFY WITHOUT DISCUSSION
# ============================================================================
# This section contains CRITICAL business logic for inventory costing.
#
# THE PROBLEM IT SOLVES:
# - Product costs (standard_cost, last_cost) are stored per PURCHASING unit ($/KG)
# - Inventory quantities are tracked in BASE unit (grams)
# - Without conversion: 3856 G * $14.99/KG = $57,801 (WRONG!)
# - With conversion: 3856 G * $0.01499/G = $57.80 (CORRECT!)
#
# KEY RULE: Cost is ALWAYS stored per reference unit (KG for mass, M for length)
#           regardless of what unit inventory is tracked in.
#
# If you need to modify this logic:
# 1. Discuss with the team first
# 2. Understand the cost/quantity relationship
# 3. Test with real data to verify COGS calculations
# 4. Check the accounting dashboard after changes
#
# Related files:
# - inventory_service.py: get_effective_cost_per_inventory_unit()
# - admin/accounting.py: COGS calculations
# ============================================================================

def get_cost_reference_unit(inventory_unit: str) -> str:
    """
    Get the reference unit that costs are stored in for a given inventory unit.

    Costs in FilaOps are ALWAYS stored per reference unit (base unit of each class):
    - Mass: $/KG (even if inventory tracks in grams)
    - Length: $/M (even if inventory tracks in mm)
    - Volume: $/L (even if inventory tracks in ml)
    - Count: $/EA

    This is standard for 3D print farms where:
    - Filament is purchased by the spool (1KG) at $/KG
    - Inventory tracks consumption in grams for precision
    - Cost calculations must convert to match inventory unit

    Args:
        inventory_unit: The unit used for inventory tracking (e.g., 'G', 'KG', 'EA')

    Returns:
        The reference unit that costs are expressed in (e.g., 'KG' for weight units)
    """
    unit = (inventory_unit or 'EA').upper().strip()
    uom_info = INLINE_UOM_CONVERSIONS.get(unit)
    if uom_info:
        return uom_info['base']
    return unit  # Unknown unit, return as-is


def convert_cost_for_unit(
    cost_per_source_unit: Optional[Decimal],
    source_unit: str,
    target_unit: str,
) -> Optional[Decimal]:
    """
    Convert cost_per_unit when quantity unit changes.

    When quantity is converted from source_unit to target_unit, the cost
    must be inversely converted to maintain accurate total cost calculations.

    Example:
        - If 1 KG = 1000 G (quantity multiplied by 1000)
        - Then $15/KG = $0.015/G (cost divided by 1000)
        - So 1000 G * $0.015/G = $15 (correct total)

    Args:
        cost_per_source_unit: Cost per unit in source unit (e.g., $/KG)
        source_unit: The unit the cost is expressed in (e.g., 'KG')
        target_unit: The unit the quantity is expressed in (e.g., 'G')

    Returns:
        Cost per target unit, or None if input cost is None
        Returns original cost if conversion fails (units incompatible)
    """
    if cost_per_source_unit is None:
        return None

    source_unit = (source_unit or 'EA').upper().strip()
    target_unit = (target_unit or 'EA').upper().strip()

    if source_unit == target_unit:
        return cost_per_source_unit

    # Get conversion info from inline table
    source_info = INLINE_UOM_CONVERSIONS.get(source_unit)
    target_info = INLINE_UOM_CONVERSIONS.get(target_unit)

    if not source_info or not target_info:
        # Unknown unit - return original cost
        return cost_per_source_unit

    if source_info['base'] != target_info['base']:
        # Incompatible units - return original cost
        return cost_per_source_unit

    # For quantity: target_qty = source_qty * (source_factor / target_factor)
    # For cost: target_cost = source_cost * (target_factor / source_factor)
    # (inverse relationship to preserve total cost)
    cost_conversion_factor = target_info['factor'] / source_info['factor']

    return cost_per_source_unit * cost_conversion_factor


def _convert_uom_inline(quantity: Decimal, from_unit: str, to_unit: str) -> Tuple[Decimal, bool]:
    """
    Convert quantity using inline conversion factors (no database lookup).
    Used as fallback when database UOM table is empty.
    
    Returns:
        Tuple of (converted_quantity, was_converted)
        - was_converted=True: Conversion succeeded
        - was_converted=False: Units unknown or incompatible
    """
    from_unit = (from_unit or 'EA').upper().strip()
    to_unit = (to_unit or 'EA').upper().strip()
    
    if from_unit == to_unit:
        return quantity, True
    
    from_info = INLINE_UOM_CONVERSIONS.get(from_unit)
    to_info = INLINE_UOM_CONVERSIONS.get(to_unit)
    
    if not from_info or not to_info:
        return quantity, False  # Unknown unit
    
    if from_info['base'] != to_info['base']:
        return quantity, False  # Incompatible bases
    
    # Convert: from_unit -> base -> to_unit
    quantity_in_base = quantity * from_info['factor']
    quantity_in_target = quantity_in_base / to_info['factor']
    
    return quantity_in_target, True


class UOMConversionError(Exception):
    """Raised when a UOM conversion fails."""
    pass


def get_uom_by_code(db: Session, code: str) -> Optional[UnitOfMeasure]:
    """
    Get a UnitOfMeasure by its code (case-insensitive).

    Args:
        db: Database session
        code: UOM code (e.g., 'KG', 'kg', 'G', 'g')

    Returns:
        UnitOfMeasure or None if not found
    """
    return db.query(UnitOfMeasure).filter(
        func.upper(UnitOfMeasure.code) == code.upper(),
        UnitOfMeasure.active.is_(True)
    ).first()


def get_conversion_factor(db: Session, from_unit: str, to_unit: str) -> Decimal:
    """
    Get the conversion factor between two units.

    Args:
        db: Database session
        from_unit: Source unit code (e.g., 'G')
        to_unit: Target unit code (e.g., 'KG')

    Returns:
        Conversion factor (multiply source quantity by this to get target)

    Raises:
        UOMConversionError: If units not found or incompatible

    The lookup itself lives in ``unit_conversion.physical_factor``. This name
    stays for its callers until they are moved onto that module. Two units of
    the ``pack`` kind (BOX, PK) are never converted to each other: a pack has
    no size until an item gives it one.
    """
    # Imported here: unit_conversion imports UOMConversionError from this module.
    from app.services.unit_conversion import physical_factor

    return physical_factor(db, from_unit, to_unit)


def convert_quantity(
    db: Session,
    quantity: Decimal,
    from_unit: str,
    to_unit: str,
) -> Decimal:
    """
    Convert a quantity from one unit to another.

    Args:
        db: Database session
        quantity: The quantity to convert
        from_unit: Source unit code (e.g., 'G' for grams)
        to_unit: Target unit code (e.g., 'KG' for kilograms)

    Returns:
        Converted quantity

    Raises:
        UOMConversionError: If units not found or incompatible

    Example:
        >>> convert_quantity(db, Decimal("225.23"), "G", "KG")
        Decimal("0.22523")
    """
    if from_unit.upper() == to_unit.upper():
        return quantity

    factor = get_conversion_factor(db, from_unit, to_unit)
    qty = Decimal(str(quantity))

    return qty * factor


def convert_quantity_with_factor(
    db: Session,
    quantity: Decimal,
    from_unit: str,
    to_unit: str,
) -> Tuple[Decimal, Decimal]:
    """
    Convert a quantity and return both the converted value and conversion factor.
    
    This is more efficient than calling convert_quantity and get_conversion_factor
    separately, as it only performs one database lookup.

    Args:
        db: Database session
        quantity: The quantity to convert
        from_unit: Source unit code (e.g., 'G' for grams)
        to_unit: Target unit code (e.g., 'KG' for kilograms)

    Returns:
        Tuple of (converted_quantity, conversion_factor)

    Raises:
        UOMConversionError: If units not found or incompatible

    Example:
        >>> convert_quantity_with_factor(db, Decimal("225.23"), "G", "KG")
        (Decimal("0.22523"), Decimal("0.001"))
    """
    if from_unit.upper() == to_unit.upper():
        return quantity, Decimal("1")

    factor = get_conversion_factor(db, from_unit, to_unit)
    qty = Decimal(str(quantity))
    converted = qty * factor

    return converted, factor


def convert_quantity_safe(
    db: Session,
    quantity: Decimal,
    from_unit: str,
    to_unit: str,
) -> Tuple[Decimal, bool]:
    """
    Safely convert a quantity, returning original if conversion fails.

    Tries database UOM lookup first, then falls back to inline conversion
    for common units (G/KG, MM/M, etc.) when database table is empty.

    Args:
        db: Database session
        quantity: The quantity to convert
        from_unit: Source unit code
        to_unit: Target unit code

    Returns:
        Tuple of (converted_quantity, was_successful)
        - was_successful=True: Conversion succeeded or units already match (no-op success)
        - was_successful=False: Conversion failed due to incompatible units

    Note:
        Same-unit conversions return (quantity, True) because the operation
        logically succeeded - no conversion was needed. Callers should treat
        both converted and same-unit results as success cases.
    """
    try:
        if from_unit.upper() == to_unit.upper():
            # Units already match - no conversion needed, but this is success
            return quantity, True
        converted = convert_quantity(db, quantity, from_unit, to_unit)
        return converted, True
    except UOMConversionError:
        # Database conversion failed - try inline fallback for common units
        return _convert_uom_inline(quantity, from_unit, to_unit)


def validate_units_compatible(db: Session, unit1: str, unit2: str) -> bool:
    """
    Check if two units are compatible (same class) and can be converted.

    Args:
        db: Database session
        unit1: First unit code
        unit2: Second unit code

    Returns:
        True if units are compatible, False otherwise
    """
    uom1 = get_uom_by_code(db, unit1)
    uom2 = get_uom_by_code(db, unit2)

    if not uom1 or not uom2:
        return False

    return uom1.uom_class == uom2.uom_class  # type: ignore[return-value]


def get_all_uom_classes(db: Session) -> list:
    """
    Get all unique UOM classes.

    Returns:
        List of class names (e.g., ['quantity', 'weight', 'length', 'time'])
    """
    result = db.query(UnitOfMeasure.uom_class).distinct().all()
    return [row[0] for row in result]


def get_units_by_class(db: Session, uom_class: str) -> list:
    """
    Get all units in a specific class.

    Args:
        db: Database session
        uom_class: The class name (e.g., 'weight')

    Returns:
        List of UnitOfMeasure objects
    """
    return db.query(UnitOfMeasure).filter(
        UnitOfMeasure.uom_class == uom_class,
        UnitOfMeasure.active.is_(True)
    ).all()


def format_quantity_with_unit(quantity: Decimal, unit: str) -> str:
    """
    Format a quantity with its unit symbol.

    Args:
        quantity: The numeric quantity
        unit: The unit code (e.g., 'KG')

    Returns:
        Formatted string (e.g., '2.5 kg')
        
    Note:
        Uses fixed-point notation to avoid scientific notation for very small values.
        Precision is limited to avoid excessively long strings.
        Strips trailing zeros and decimal point for cleaner display.
    """
    # Convert to string with fixed-point notation (avoids scientific notation)
    # Limit precision to prevent excessively long strings
    qty_str = format(quantity, f'.{MAX_DECIMAL_PLACES}f')
    
    # Strip trailing zeros after decimal point
    if '.' in qty_str:
        qty_str = qty_str.rstrip('0').rstrip('.')
    
    return f"{qty_str} {unit.lower()}"


def format_conversion_note(
    original_qty: Decimal,
    original_unit: str,
    converted_qty: Decimal,
    converted_unit: str,
    product_name: Optional[str] = None,
) -> str:
    """
    Format a conversion note for transaction records.

    Args:
        original_qty: Original quantity
        original_unit: Original unit code
        converted_qty: Converted quantity
        converted_unit: Target unit code
        product_name: Optional product name

    Returns:
        Formatted note string

    Example:
        "225.23 G (= 0.22523 KG) of PLA-BLACK-1KG"
    """
    orig = format_quantity_with_unit(original_qty, original_unit)
    conv = format_quantity_with_unit(converted_qty, converted_unit)

    note = f"{orig} (= {conv})"
    if product_name:
        note += f" of {product_name}"

    return note

def get_product_consumption_uom(db: Session, product_id: int, default_unit: str = "KG") -> str:
    """
    Get the consumption UOM for a product.
    
    For materials (is_raw_material=True), this is the unit used when consuming
    from inventory. For other products, returns the product's unit or default.
    
    Args:
        db: Database session
        product_id: Product ID
        default_unit: Default unit if product not found or unit is missing
    
    Returns:
        Unit code (e.g., 'KG', 'G', 'EA')
    
    Note:
        This function is safe to call even if product doesn't exist.
        It will return the default_unit in that case.
    """
    from app.models.product import Product
    
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return default_unit
    
    # Normalize unit (handle None, empty string, or default "EA")
    unit = (product.unit or "").strip().upper()
    
    # For raw materials: if unit is missing/empty/default "EA", use KG
    if product.is_raw_material:  # type: ignore[truthy-bool]
        if not unit or unit == "EA":  # EA is the default, treat as "no unit set"
            return "KG"
        return unit
    
    # For other products, use their unit or default
    return unit if unit else default_unit