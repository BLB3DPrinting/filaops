"""Axis-type resolver registry. Module-level dict, keyed by type_name."""
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Product
    from app.models.manufacturing import RoutingOperationMaterial
    from app.services.variant_axis.types import AxisOption

_REGISTRY: dict[str, "AxisTypeResolver"] = {}


@runtime_checkable
class AxisTypeResolver(Protocol):
    type_name: str = ""  # sentinel; implementing classes must set their own

    def list_options(
        self,
        db: "Session",
        *,
        template: "Product",
        routing_material: "RoutingOperationMaterial",
    ) -> list["AxisOption"]: ...

    def resolve_to_component(
        self, db: "Session", *, value: dict
    ) -> "Product": ...

    def synthesize_legacy(
        self, *, variant_metadata_legacy: dict
    ) -> dict | None: ...


def register(resolver: AxisTypeResolver) -> None:
    """Register a resolver under its type_name.

    If a resolver with the same type_name is already registered, it is
    replaced (last-write-wins). Tests rely on this for setup/teardown
    isolation; production code should not register the same type_name twice.
    """
    _REGISTRY[resolver.type_name] = resolver


def get(type_name: str) -> AxisTypeResolver:
    """Lookup. Raises KeyError if type_name not registered."""
    return _REGISTRY[type_name]


def all_types() -> list[str]:
    """Return registered type_names in insertion order."""
    return list(_REGISTRY.keys())
