"""
Plugin registry for FilaOps extension points.

Core ships with tier="community" and no features enabled.
Plugins (e.g. filaops-pro) call set_tier() / set_features() at startup
via their register(app) entry point to advertise capabilities.

Usage from a plugin's register():
    from app.core.plugin_registry import set_tier, set_features
    set_tier("professional")
    set_features(["b2b_portal", "quote_engine", "advanced_tax"])
"""

_tier: str = "community"
_features: list[str] = []


def get_tier() -> str:
    return _tier


def get_features() -> list[str]:
    return list(_features)


def set_tier(tier: str) -> None:
    global _tier
    _tier = tier


def set_features(features: list[str]) -> None:
    global _features
    _features = list(features)


def reset() -> None:
    """Reset to defaults. Used by tests."""
    global _tier, _features
    _tier = "community"
    _features = []
