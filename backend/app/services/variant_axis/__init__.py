"""Variant axis package — registry + per-axis-type resolvers.

Resolvers register themselves on import. Add a new axis type by creating
a module here and importing it from this file's bottom.
"""
from app.services.variant_axis import registry  # noqa: F401

# Resolvers are registered by importing their modules. Order doesn't matter.
# (Imports added in later tasks: material_color, component_template.)
