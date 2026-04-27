"""Axis-type resolver registry. Module-level dict, keyed by type_name."""
from typing import Protocol, runtime_checkable

_REGISTRY: dict[str, "AxisTypeResolver"] = {}


@runtime_checkable
class AxisTypeResolver(Protocol):
    type_name: str


def register(resolver: AxisTypeResolver) -> None:
    """Register a resolver under its type_name. Last-write-wins for tests."""
    _REGISTRY[resolver.type_name] = resolver


def get(type_name: str) -> AxisTypeResolver:
    """Lookup. Raises KeyError if type_name not registered."""
    return _REGISTRY[type_name]


def all_types() -> list[str]:
    """Return registered type_names in insertion order."""
    return list(_REGISTRY.keys())
