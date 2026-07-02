"""
Feature Flag System for FilaOps

Historically this module also housed a ``require_tier`` decorator used as an
API gate. That gate was a no-op (it short-circuited whenever
``LICENSING_ENABLED`` was False) and has been RETIRED — live PRO feature
gating now lives in ``app.core.licensing_gate.require_feature``, which reads
the plugin registry and fails closed. This module retains only the resource
LIMIT helpers (seats/printers/sites), still guarded by ``LICENSING_ENABLED``.
"""
from enum import Enum
from typing import Dict, List
from fastapi import HTTPException
from sqlalchemy.orm import Session

# ============================================================================
# MASTER SWITCH - Set to True when ready to enforce licensing
# ============================================================================
LICENSING_ENABLED = False  # Everyone gets all features for now!

# ============================================================================
# TIER LIMITS - Resource limits per subscription tier
# ============================================================================
# -1 means unlimited
TIER_LIMITS: Dict[str, Dict[str, int]] = {
    "community": {
        "users": 1,           # Single user (the admin)
        "printers": 4,        # Up to 4 printers
        "sites": 1,           # Single location
        "api_rate_limit": 100,  # Requests per minute
    },
    "professional": {
        "users": -1,          # Unlimited users
        "printers": -1,       # Unlimited printers
        "sites": 1,           # Single location (multi-site is Enterprise)
        "min_seats": 2,       # Minimum 2 seats to purchase
        "api_rate_limit": 1000,
    },
    "enterprise": {
        "users": -1,          # Unlimited
        "printers": -1,       # Unlimited
        "sites": -1,          # Unlimited locations
        "api_rate_limit": -1, # Unlimited
    },
}

class FeatureTier(str, Enum):
    """Subscription tiers"""
    COMMUNITY = "community"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    
    # Aliases for backward compatibility
    PRO = "professional"  # Same as PROFESSIONAL

# ============================================================================
# Feature Definitions
# ============================================================================
# NOTE: For now, ALL features are marked as "community" so everyone gets them.
# When ready to monetize, just change the tier values below.
# ============================================================================

FEATURE_FLAGS: Dict[str, Dict] = {
    # ========================================================================
    # Quality - Traceability (FREE FOREVER)
    # ========================================================================
    "traceability_forward": {
        "name": "Forward Traceability",
        "tier": FeatureTier.COMMUNITY,
        "description": "Trace materials forward from spool to finished products",
        "category": "quality",
    },
    "traceability_backward": {
        "name": "Backward Traceability",
        "tier": FeatureTier.COMMUNITY,
        "description": "Trace finished products back to source materials",
        "category": "quality",
    },
    "traceability_export": {
        "name": "DHR Report Export",
        "tier": FeatureTier.COMMUNITY,
        "description": "Export Device History Records as PDF/CSV",
        "category": "quality",
    },
    "quality_audit_log": {
        "name": "Quality Audit Log",
        "tier": FeatureTier.COMMUNITY,
        "description": "Track all quality-related changes",
        "category": "quality",
    },
    
    # ========================================================================
    # Quality - Advanced (Future: Professional Tier)
    # ========================================================================
    # When ready to monetize, change these to FeatureTier.PROFESSIONAL
    "recall_impact_calculator": {
        "name": "Recall Impact Calculator",
        "tier": FeatureTier.COMMUNITY,  # Future: PROFESSIONAL tier
        "description": "Calculate scope of material recalls",
        "category": "quality",
    },
    "quality_holds": {
        "name": "Quality Holds & Quarantine",
        "tier": FeatureTier.COMMUNITY,  # Future: PROFESSIONAL tier
        "description": "Put materials/products on quality hold",
        "category": "quality",
    },
    "traceability_alerts": {
        "name": "Material Usage Alerts",
        "tier": FeatureTier.COMMUNITY,  # Future: PROFESSIONAL tier
        "description": "Email notifications when specific materials are used",
        "category": "quality",
    },
    "advanced_reports": {
        "name": "Advanced Quality Reports",
        "tier": FeatureTier.COMMUNITY,  # Future: PROFESSIONAL tier
        "description": "Custom quality reports and analytics",
        "category": "quality",
    },
    
    # ========================================================================
    # Quality - Enterprise (Future: Enterprise Tier)
    # ========================================================================
    # When ready to monetize, change these to FeatureTier.ENTERPRISE
    "traceability_webhooks": {
        "name": "Traceability API Webhooks",
        "tier": FeatureTier.COMMUNITY,  # Future: ENTERPRISE tier
        "description": "Real-time webhooks for material usage events",
        "category": "quality",
    },
    "multi_site_traceability": {
        "name": "Multi-Site Traceability",
        "tier": FeatureTier.COMMUNITY,  # Future: ENTERPRISE tier
        "description": "Trace materials across multiple facilities",
        "category": "quality",
    },
    "spc_charts": {
        "name": "Statistical Process Control",
        "tier": FeatureTier.COMMUNITY,  # Future: ENTERPRISE tier
        "description": "Real-time SPC charts and control limits",
        "category": "quality",
    },
}

# ============================================================================
# Convenience Lists
# ============================================================================

COMMUNITY_FEATURES = [
    code for code, feature in FEATURE_FLAGS.items() 
    if feature["tier"] == FeatureTier.COMMUNITY
]

PROFESSIONAL_FEATURES = [
    code for code, feature in FEATURE_FLAGS.items() 
    if feature["tier"] in [FeatureTier.COMMUNITY, FeatureTier.PROFESSIONAL]
]

ENTERPRISE_FEATURES = list(FEATURE_FLAGS.keys())  # All features

# ============================================================================
# Feature Access Functions
# ============================================================================

def has_feature(feature_code: str, user_tier: str = "community") -> bool:
    """
    Check if a user's tier has access to a feature.
    
    If LICENSING_ENABLED = False, always returns True (everyone gets everything).
    If LICENSING_ENABLED = True, checks tier hierarchy.
    
    Args:
        feature_code: Feature identifier (e.g., "traceability_forward")
        user_tier: User's subscription tier
    
    Returns:
        True if user has access, False otherwise
    """
    # If licensing is disabled, everyone gets everything!
    if not LICENSING_ENABLED:
        return True
    
    # Check if feature exists
    if feature_code not in FEATURE_FLAGS:
        return False
    
    feature = FEATURE_FLAGS[feature_code]
    tier_order = ["community", "professional", "enterprise"]
    
    required_tier_index = tier_order.index(feature["tier"])
    user_tier_index = tier_order.index(user_tier.lower())
    
    return user_tier_index >= required_tier_index

def get_features_for_tier(tier: str) -> List[str]:
    """
    Get all feature codes available for a tier.
    
    Args:
        tier: Subscription tier
    
    Returns:
        List of feature codes
    """
    if tier == FeatureTier.COMMUNITY:
        return COMMUNITY_FEATURES
    elif tier == FeatureTier.PROFESSIONAL:
        return PROFESSIONAL_FEATURES
    elif tier == FeatureTier.ENTERPRISE:
        return ENTERPRISE_FEATURES
    return COMMUNITY_FEATURES

def get_features_by_category(category: str) -> Dict[str, Dict]:
    """
    Get all features in a category.
    
    Args:
        category: Category name (e.g., "quality")
    
    Returns:
        Dict of feature_code -> feature_info
    """
    return {
        code: feature 
        for code, feature in FEATURE_FLAGS.items() 
        if feature.get("category") == category
    }

# ============================================================================
# Backward Compatibility (Legacy API)
# ============================================================================

# Alias for backward compatibility
Tier = FeatureTier

def get_current_tier(db: Session, user) -> FeatureTier:
    """
    Get the current user's subscription tier.
    
    Args:
        db: Database session
        user: Current user object
    
    Returns:
        User's tier (defaults to COMMUNITY if licensing disabled)
    """
    # If licensing is disabled, everyone is enterprise (all features)
    if not LICENSING_ENABLED:
        return FeatureTier.ENTERPRISE
    
    # License key validation available in FilaOps Pro
    return FeatureTier.COMMUNITY

def get_available_features(tier: FeatureTier) -> List[str]:
    """
    Get list of feature codes available for a tier.
    
    Args:
        tier: Subscription tier
    
    Returns:
        List of feature codes
    """
    return get_features_for_tier(tier.value)

# NOTE: ``require_tier`` (a decorator-based API gate) was removed in PR-D1.
# It short-circuited whenever LICENSING_ENABLED was False, so every use was a
# silent no-op. Live PRO gating is now ``app.core.licensing_gate.require_feature``.


# ============================================================================
# Resource Limit Checking
# ============================================================================

def get_tier_limit(tier: str, resource: str) -> int:
    """
    Get the limit for a resource at a given tier.

    Args:
        tier: Subscription tier (community, professional, enterprise)
        resource: Resource name (users, printers, sites)

    Returns:
        Limit value (-1 for unlimited)
    """
    tier_lower = tier.lower()
    if tier_lower not in TIER_LIMITS:
        tier_lower = "community"
    return TIER_LIMITS[tier_lower].get(resource, -1)


def check_resource_limit(
    db: Session,
    resource: str,
    current_count: int,
    tier: str = "community"
) -> dict:
    """
    Check if a resource limit would be exceeded.

    Args:
        db: Database session
        resource: Resource name (users, printers, sites)
        current_count: Current count of the resource
        tier: User's subscription tier

    Returns:
        Dict with:
        - allowed: bool - whether adding one more is allowed
        - limit: int - the limit for this tier (-1 = unlimited)
        - current: int - current count
        - remaining: int - how many more can be added (-1 = unlimited)
        - upgrade_message: str - message if limit reached
    """
    limit = get_tier_limit(tier, resource)

    # -1 means unlimited
    if limit == -1:
        return {
            "allowed": True,
            "limit": -1,
            "current": current_count,
            "remaining": -1,
            "upgrade_message": None,
        }

    allowed = current_count < limit
    remaining = max(0, limit - current_count)

    upgrade_message = None
    if not allowed:
        resource_name = resource.replace("_", " ").title()
        upgrade_message = (
            f"You've reached the {resource_name} limit ({limit}) for the Community tier. "
            f"Upgrade to Pro for unlimited {resource}."
        )

    return {
        "allowed": allowed,
        "limit": limit,
        "current": current_count,
        "remaining": remaining,
        "upgrade_message": upgrade_message,
    }


def enforce_resource_limit(
    db: Session,
    resource: str,
    current_count: int,
    tier: str = "community"
) -> None:
    """
    Enforce a resource limit - raises HTTPException if limit exceeded.

    Args:
        db: Database session
        resource: Resource name (users, printers, sites)
        current_count: Current count of the resource
        tier: User's subscription tier

    Raises:
        HTTPException: 403 if limit exceeded
    """
    # If licensing is disabled, don't enforce limits
    if not LICENSING_ENABLED:
        return

    result = check_resource_limit(db, resource, current_count, tier)

    if not result["allowed"]:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "TIER_LIMIT_EXCEEDED",
                "message": result["upgrade_message"],
                "resource": resource,
                "limit": result["limit"],
                "current": result["current"],
                "tier": tier,
            }
        )


def get_usage_summary(db: Session, tier: str = "community") -> dict:
    """
    Get a summary of resource usage vs limits.

    Useful for displaying in settings/dashboard.

    Args:
        db: Database session
        tier: User's subscription tier

    Returns:
        Dict with usage info for each limited resource
    """
    # Import here to avoid circular imports
    from app.models.user import User
    from app.models.printer import Printer

    # Count current resources
    user_count = db.query(User).filter(
        User.account_type.in_(["admin", "operator"]),
        User.status == "active"
    ).count()

    printer_count = db.query(Printer).filter(
        Printer.active.is_(True)
    ).count()

    return {
        "tier": tier,
        "licensing_enabled": LICENSING_ENABLED,
        "resources": {
            "users": check_resource_limit(db, "users", user_count, tier),
            "printers": check_resource_limit(db, "printers", printer_count, tier),
        },
    }
