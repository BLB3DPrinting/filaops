"""Shared types for variant-axis resolvers."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AxisOption:
    """One selectable option on a variant axis (one row in the matrix UI).

    `value` is the type-specific payload that gets stored verbatim in
    Product.variant_metadata.axis_selections[<id>].value and on
    SalesOrderLine.configuration. The resolver is the only code that
    interprets it.

    AxisOption is intentionally not hashable: the dict fields (`value`, `extras`)
    make a stable hash impossible. Use list operations, not sets, to deduplicate.
    """
    value: dict[str, Any]
    label: str  # human-readable (e.g., "PLA Basic — Black", "M5 × 12mm")
    preview_sku: str | None = None  # for matrix preview cells
    preview_name: str | None = None  # for matrix preview cells
    extras: dict[str, Any] = field(default_factory=dict)  # axis-specific (e.g., color_hex)

    # Explicit: AxisOption is equality-comparable but NOT hashable.
    # The dict fields (value, extras) raise TypeError on hash(). Setting
    # __hash__ = None makes the class unhashable at the type level rather
    # than failing only at hash-call time, which is the cleaner contract.
    __hash__ = None  # type: ignore[assignment]
