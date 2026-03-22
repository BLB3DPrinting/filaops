#!/usr/bin/env python3
"""
Generate docs/SCHEMA-REFERENCE.md from SQLAlchemy model definitions.

Scans backend/app/models/*.py, uses Python AST to extract model classes,
columns, constraints, and relationships, then generates a Markdown reference.

Usage:
    cd backend
    python scripts/generate_schema_reference.py
"""
import ast
import os
import re
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODELS_DIR = Path(__file__).resolve().parent.parent / "app" / "models"
VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
OUTPUT_FILE = Path(__file__).resolve().parent.parent.parent / "docs" / "SCHEMA-REFERENCE.md"

# Category mapping: model class name -> category
CATEGORY_MAP = {
    # Core ERP
    "Product": "Core ERP Models",
    "BOM": "Core ERP Models",
    "BOMLine": "Core ERP Models",
    "Inventory": "Core ERP Models",
    "InventoryTransaction": "Core ERP Models",
    "InventoryLocation": "Core ERP Models",
    "SalesOrder": "Core ERP Models",
    "SalesOrderLine": "Core ERP Models",
    "Payment": "Core ERP Models",
    "Vendor": "Core ERP Models",
    "PurchaseOrder": "Core ERP Models",
    "PurchaseOrderLine": "Core ERP Models",
    "ItemCategory": "Core ERP Models",
    # Manufacturing
    "ProductionOrder": "Manufacturing Models",
    "ProductionOrderOperation": "Manufacturing Models",
    "ProductionOrderOperationMaterial": "Manufacturing Models",
    "ScrapRecord": "Manufacturing Models",
    "WorkCenter": "Manufacturing Models",
    "Resource": "Manufacturing Models",
    "Routing": "Manufacturing Models",
    "RoutingOperation": "Manufacturing Models",
    "RoutingOperationMaterial": "Manufacturing Models",
    "Printer": "Manufacturing Models",
    "PrintJob": "Manufacturing Models",
    # User & Auth
    "User": "User & Auth Models",
    "RefreshToken": "User & Auth Models",
    "PasswordResetRequest": "User & Auth Models",
    "Customer": "User & Auth Models",
    # Quote & Sales
    "Quote": "Quote & Sales Models",
    "QuoteFile": "Quote & Sales Models",
    "QuoteMaterial": "Quote & Sales Models",
    # Material & Traceability
    "MaterialType": "Material & Traceability Models",
    "Color": "Material & Traceability Models",
    "MaterialColor": "Material & Traceability Models",
    "MaterialInventory": "Material & Traceability Models",
    "MaterialSpool": "Material & Traceability Models",
    "ProductionOrderSpool": "Material & Traceability Models",
    "SerialNumber": "Material & Traceability Models",
    "MaterialLot": "Material & Traceability Models",
    "ProductionLotConsumption": "Material & Traceability Models",
    "CustomerTraceabilityProfile": "Material & Traceability Models",
    # MRP
    "MRPRun": "MRP Models",
    "PlannedOrder": "MRP Models",
    # Document
    "PurchaseOrderDocument": "Document Models",
    "VendorItem": "Document Models",
    # Settings
    "CompanySettings": "Settings Models",
    # Events
    "OrderEvent": "Event Models",
    "PurchasingEvent": "Event Models",
    "ShippingEvent": "Event Models",
    # UOM
    "UnitOfMeasure": "UOM Models",
    # Accounting
    "GLAccount": "Accounting Models",
    "GLFiscalPeriod": "Accounting Models",
    "GLJournalEntry": "Accounting Models",
    "GLJournalEntryLine": "Accounting Models",
    # Tax
    "TaxRate": "Tax Models",
    # Other
    "AdjustmentReason": "Reference Data Models",
    "ScrapReason": "Reference Data Models",
    "MaintenanceLog": "Reference Data Models",
}

# Ordered list of categories for TOC and output
CATEGORY_ORDER = [
    "Core ERP Models",
    "Manufacturing Models",
    "User & Auth Models",
    "Quote & Sales Models",
    "Material & Traceability Models",
    "MRP Models",
    "Document Models",
    "Settings Models",
    "Event Models",
    "UOM Models",
    "Accounting Models",
    "Tax Models",
    "Reference Data Models",
]

# ---------------------------------------------------------------------------
# AST Extraction
# ---------------------------------------------------------------------------


def _get_string_value(node):
    """Extract a string value from an AST node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "<f-string>"
    return None


def _get_constant_value(node):
    """Extract a constant value from an AST node (str, int, float, bool)."""
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        if isinstance(node.operand, ast.Constant):
            return repr(-node.operand.value)
    if isinstance(node, ast.Attribute):
        # e.g. func.now()
        return None
    if isinstance(node, ast.Call):
        return None
    if isinstance(node, ast.Lambda):
        return None
    return None


def _extract_column_type(call_node):
    """Extract the column type string from a Column() call's first positional arg."""
    if not call_node.args:
        return "Unknown"

    first_arg = call_node.args[0]

    # Handle Computed("expr") as a type
    if isinstance(first_arg, ast.Call) and _get_name(first_arg.func) == "Computed":
        expr = ""
        if first_arg.args and isinstance(first_arg.args[0], ast.Constant):
            expr = first_arg.args[0].value
        return f"Computed({expr})"

    type_name = _get_name(first_arg)

    if type_name is None:
        # Might be a type with args like String(50)
        if isinstance(first_arg, ast.Call):
            type_name = _get_name(first_arg.func)
            if type_name and first_arg.args:
                args_str = ", ".join(
                    str(a.value) if isinstance(a, ast.Constant) else "?"
                    for a in first_arg.args
                )
                return f"{type_name}({args_str})"
            return type_name or "Unknown"
        return "Unknown"

    # Check if first arg is a Call (e.g. String(50))
    if isinstance(first_arg, ast.Call) and first_arg.args:
        args_str = ", ".join(
            str(a.value) if isinstance(a, ast.Constant) else "?"
            for a in first_arg.args
        )
        return f"{type_name}({args_str})"

    # Check for type with keyword args like DateTime(timezone=False)
    if isinstance(first_arg, ast.Call) and first_arg.keywords:
        kw_str = ", ".join(
            f"{k.arg}={_get_constant_value(k.value) or '?'}"
            for k in first_arg.keywords
        )
        return f"{type_name}({kw_str})"

    return type_name


def _get_name(node):
    """Get the name from a Name or Attribute AST node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _extract_constraints(call_node):
    """Extract constraints from a Column() call."""
    constraints = []

    # Check positional args for ForeignKey
    for arg in call_node.args:
        if isinstance(arg, ast.Call) and _get_name(arg.func) == "ForeignKey":
            if arg.args:
                fk_target = _get_string_value(arg.args[0])
                if fk_target:
                    constraints.append(f"FK->{fk_target}")

        # Computed column
        if isinstance(arg, ast.Call) and _get_name(arg.func) == "Computed":
            constraints.append("COMPUTED")

    # Check keyword args
    for kw in call_node.keywords:
        if kw.arg == "primary_key" and _is_true(kw.value):
            constraints.append("PK")
        elif kw.arg == "nullable" and _is_false(kw.value):
            constraints.append("NOT NULL")
        elif kw.arg == "unique" and _is_true(kw.value):
            constraints.append("UNIQUE")
        elif kw.arg == "index" and _is_true(kw.value):
            constraints.append("INDEX")
        elif kw.arg == "default":
            val = _get_constant_value(kw.value)
            if val is not None:
                constraints.append(f"DEFAULT {val}")
            elif isinstance(kw.value, ast.Lambda):
                constraints.append("DEFAULT utcnow")
            elif isinstance(kw.value, ast.Call):
                func_name = _get_name(kw.value.func)
                if func_name:
                    constraints.append(f"DEFAULT {func_name}()")
        elif kw.arg == "server_default":
            if isinstance(kw.value, ast.Call):
                func_name = _get_name(kw.value.func)
                if func_name:
                    constraints.append(f"DEFAULT {func_name}()")
            else:
                val = _get_constant_value(kw.value)
                if val:
                    constraints.append(f"DEFAULT {val}")

    return constraints


def _is_true(node):
    """Check if an AST node represents True."""
    if isinstance(node, ast.Constant) and node.value is True:
        return True
    return False


def _is_false(node):
    """Check if an AST node represents False."""
    if isinstance(node, ast.Constant) and node.value is False:
        return True
    return False


def _infer_description(col_name, col_type, constraints):
    """Infer a short description from column name and constraints."""
    constraint_str = ", ".join(constraints)

    # Primary key
    if "PK" in constraints:
        return "Primary key"

    # Foreign key
    for c in constraints:
        if c.startswith("FK->"):
            target = c[4:]
            return f"FK reference to {target}"

    # Common names
    name_descriptions = {
        "created_at": "Creation timestamp",
        "updated_at": "Last update timestamp",
        "created_by": "Creator reference",
        "updated_by": "Last updater reference",
        "name": "Display name",
        "code": "Unique code identifier",
        "description": "Description text",
        "notes": "Additional notes",
        "status": "Current status",
        "active": "Active flag",
        "is_active": "Active flag",
        "email": "Email address",
        "sku": "Stock keeping unit",
        "quantity": "Quantity value",
        "unit": "Unit of measure",
        "version": "Version number",
        "revision": "Revision identifier",
        "sequence": "Sort order / sequence",
        "total_cost": "Total cost amount",
        "order_number": "Order number identifier",
        "type": "Type classifier",
        "last_login_at": "Last login timestamp",
        "approved_at": "Approval timestamp",
        "approved_by": "Approver reference",
        "completed_at": "Completion timestamp",
        "closed_at": "Closure timestamp",
        "closed_by": "User who closed",
        "posted_at": "Posting timestamp",
        "posted_by": "User who posted",
        "voided_at": "Void timestamp",
        "voided_by": "User who voided",
        "void_reason": "Reason for voiding",
        "revoked": "Revocation flag",
        "revoked_at": "Revocation timestamp",
        "expires_at": "Expiration timestamp",
        "on_hand_quantity": "Physical quantity on hand",
        "allocated_quantity": "Quantity allocated to orders",
        "available_quantity": "Quantity available (on_hand - allocated)",
        "selling_price": "Selling price",
        "standard_cost": "Standard cost for costing",
        "average_cost": "Running average cost",
        "last_cost": "Most recent purchase cost",
        "image_url": "Product image URL",
        "is_public": "Public visibility flag",
    }

    if col_name in name_descriptions:
        return name_descriptions[col_name]

    # Pattern-based inference
    if col_name.endswith("_id") and col_name != "id":
        ref_name = col_name[:-3].replace("_", " ").title()
        return f"{ref_name} reference"
    if col_name.endswith("_at"):
        label = col_name[:-3].replace("_", " ").title()
        return f"{label} timestamp"
    if col_name.endswith("_date"):
        label = col_name[:-5].replace("_", " ").title()
        return f"{label} date"
    if col_name.startswith("is_"):
        label = col_name[3:].replace("_", " ").title()
        return f"{label} flag"
    if col_name.startswith("has_"):
        label = col_name[4:].replace("_", " ").title()
        return f"Has {label} flag"
    if col_name.startswith("track_"):
        label = col_name[6:].replace("_", " ").title()
        return f"Track {label} flag"

    # Default: humanize the column name
    return col_name.replace("_", " ").capitalize()


def _extract_relationship_info(call_node):
    """Extract relationship target and cardinality hints from a relationship() call."""
    if not call_node.args:
        return None, None

    target = _get_string_value(call_node.args[0])
    if target is None and isinstance(call_node.args[0], ast.Constant):
        target = str(call_node.args[0].value)
    if target is None:
        return None, None

    uselist = None
    back_populates = None
    backref = None

    for kw in call_node.keywords:
        if kw.arg == "uselist":
            if _is_false(kw.value):
                uselist = False
            elif _is_true(kw.value):
                uselist = True
        elif kw.arg == "back_populates":
            back_populates = _get_string_value(kw.value)
        elif kw.arg == "backref":
            backref = _get_string_value(kw.value)

    return target, uselist


def _infer_cardinality(attr_name, target_model, uselist, has_fk_to_target, model_columns):
    """Infer relationship cardinality."""
    if uselist is False:
        return "one-to-one"

    # If this model has a FK column named <attr>_id or pointing at target's table,
    # it's the "many" side -> many-to-one
    fk_col_name = f"{attr_name}_id"
    if fk_col_name in model_columns:
        return "many-to-one"

    # Check if any column has a FK to the target (heuristic)
    if has_fk_to_target:
        return "many-to-one"

    return "one-to-many"


def parse_model_file(filepath):
    """Parse a single model file and extract model definitions."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    models = []
    filename = os.path.basename(filepath)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        # Check if class inherits from Base
        inherits_base = False
        for base in node.bases:
            name = _get_name(base)
            if name == "Base":
                inherits_base = True
                break
        if not inherits_base:
            continue

        model_info = {
            "class_name": node.name,
            "tablename": None,
            "file": filename,
            "lineno": node.lineno,
            "columns": [],
            "relationships": [],
            "column_names": set(),
            "fk_targets": set(),  # set of table names this model has FKs to
        }

        # Extract __tablename__ and columns/relationships from class body
        for item in node.body:
            # __tablename__
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        model_info["tablename"] = _get_string_value(item.value)

                    # Column assignments: name = Column(...)
                    if isinstance(target, ast.Name) and isinstance(item.value, ast.Call):
                        func_name = _get_name(item.value.func)

                        if func_name == "Column":
                            col_name = target.id
                            col_type = _extract_column_type(item.value)
                            constraints = _extract_constraints(item.value)
                            description = _infer_description(col_name, col_type, constraints)

                            model_info["columns"].append({
                                "name": col_name,
                                "type": col_type,
                                "constraints": constraints,
                                "description": description,
                            })
                            model_info["column_names"].add(col_name)

                            # Track FK targets
                            for c in constraints:
                                if c.startswith("FK->"):
                                    table_col = c[4:]
                                    table = table_col.split(".")[0]
                                    model_info["fk_targets"].add(table)

                        elif func_name == "relationship":
                            target_model, uselist = _extract_relationship_info(item.value)
                            if target_model:
                                model_info["relationships"].append({
                                    "attr_name": target.id,
                                    "target": target_model,
                                    "uselist": uselist,
                                })

        # Skip classes without __tablename__ (not actual mapped models)
        if model_info["tablename"] is None:
            continue

        models.append(model_info)

    return models


# ---------------------------------------------------------------------------
# Markdown Generation
# ---------------------------------------------------------------------------


def generate_markdown(all_models, version):
    """Generate the full Markdown document."""
    # Group models by category
    categorized = {}
    for cat in CATEGORY_ORDER:
        categorized[cat] = []

    uncategorized = []
    for m in all_models:
        cat = CATEGORY_MAP.get(m["class_name"])
        if cat and cat in categorized:
            categorized[cat].append(m)
        else:
            uncategorized.append(m)

    # Add uncategorized to Reference Data Models
    if uncategorized:
        if "Reference Data Models" not in categorized:
            categorized["Reference Data Models"] = []
        categorized["Reference Data Models"].extend(uncategorized)

    # Remove empty categories
    active_categories = [(cat, models) for cat, models in categorized.items() if models]

    total_models = sum(len(models) for _, models in active_categories)

    lines = []
    lines.append("<!-- AUTO-GENERATED — Do not edit manually. Regenerate: cd backend && python scripts/generate_schema_reference.py -->")
    lines.append("")
    lines.append("# FilaOps Database Schema Reference")
    lines.append("")
    lines.append(f"**Generated:** {date.today().isoformat()}")
    lines.append(f"**Source:** FilaOps Core v{version}")
    lines.append(f"**Total Models:** {total_models} (Core only)")
    lines.append("**Purpose:** AI knowledge source for codebase understanding")
    lines.append("")
    lines.append("> This is the **Core (Open Source)** schema reference.")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Table of Contents
    lines.append("## Table of Contents")
    lines.append("")
    for i, (cat, models) in enumerate(active_categories, 1):
        # GitHub anchor: lowercase, spaces to hyphens, strip non-alnum except hyphens
        anchor = re.sub(r"[^a-z0-9 -]", "", cat.lower()).replace(" ", "-")
        anchor = re.sub(r"-{2,}", "-", anchor)
        count = len(models)
        lines.append(f"{i}. [{cat}](#{anchor}) ({count} {'model' if count == 1 else 'models'})")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Model sections
    for cat, models in active_categories:
        lines.append(f"## {cat}")
        lines.append("")

        for m in models:
            lines.append(f"### {m['class_name']}")
            lines.append("")
            lines.append(
                f"**Table:** `{m['tablename']}` | **Tier:** Core | **File:** `{m['file']}:{m['lineno']}`"
            )
            lines.append("")

            if m["columns"]:
                lines.append("| Column | Type | Constraints | Description |")
                lines.append("| ------ | ---- | ----------- | ----------- |")
                for col in m["columns"]:
                    constraints_str = ", ".join(col["constraints"]) if col["constraints"] else ""
                    lines.append(
                        f"| {col['name']} | {col['type']} | {constraints_str} | {col['description']} |"
                    )
                lines.append("")

            if m["relationships"]:
                lines.append("**Relationships:**")
                lines.append("")
                for rel in m["relationships"]:
                    cardinality = _infer_cardinality(
                        rel["attr_name"],
                        rel["target"],
                        rel["uselist"],
                        False,
                        m["column_names"],
                    )
                    lines.append(f"- `{rel['attr_name']}` -> {rel['target']} ({cardinality})")
                lines.append("")

            lines.append("---")
            lines.append("")

    # Summary Statistics
    lines.append("## Summary Statistics")
    lines.append("")
    lines.append("| Category | Models | Tables |")
    lines.append("|----------|--------|--------|")

    total_m = 0
    total_t = 0
    for cat, models in active_categories:
        num_models = len(models)
        num_tables = len(set(m["tablename"] for m in models))
        total_m += num_models
        total_t += num_tables
        lines.append(f"| {cat} | {num_models} | {num_tables} |")

    lines.append(f"| **Total** | **{total_m}** | **{total_t}** |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    # Read version
    version = "unknown"
    if VERSION_FILE.exists():
        version = VERSION_FILE.read_text().strip()

    # Scan model files
    all_models = []
    model_files = sorted(MODELS_DIR.glob("*.py"))

    for filepath in model_files:
        if filepath.name == "__init__.py":
            continue
        if filepath.name.startswith("__"):
            continue

        models = parse_model_file(filepath)
        all_models.extend(models)

    # Sort models within each file by line number (already in file order from AST)
    # but sort across files by class name for consistency within categories
    all_models.sort(key=lambda m: m["class_name"])

    # Generate markdown
    md = generate_markdown(all_models, version)

    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(md, encoding="utf-8")

    print(f"Generated {OUTPUT_FILE}")
    print(f"  Models: {len(all_models)}")
    print(f"  Version: v{version}")


if __name__ == "__main__":
    main()
