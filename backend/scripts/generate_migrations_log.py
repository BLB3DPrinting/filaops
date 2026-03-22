#!/usr/bin/env python3
"""Generate docs/MIGRATIONS-LOG.md from migration files.

Usage:
    cd backend
    python scripts/generate_migrations_log.py

Scans backend/migrations/versions/*.py, extracts metadata, and produces
a chronological Markdown log at docs/MIGRATIONS-LOG.md.

Uses only stdlib: ast, re, os, pathlib, datetime.
"""

import ast
import re
from pathlib import Path
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
VERSIONS_DIR = BACKEND_DIR / "migrations" / "versions"
OUTPUT_PATH = BACKEND_DIR.parent / "docs" / "MIGRATIONS-LOG.md"
VERSION_FILE = BACKEND_DIR / "VERSION"


# ---------------------------------------------------------------------------
# Feature-area keyword map (order matters — first match wins)
# ---------------------------------------------------------------------------
FEATURE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Initial Schema", ["initial_postgres_schema", "baseline", "stamp_existing"]),
    ("Accounting", ["accounting", "gl_", "fiscal", "chart_of_accounts", "journal",
                     "inventory_accounts", "je_link"]),
    ("Tax", ["tax_rate", "tax"]),
    ("Manufacturing", ["production", "operation", "work_center", "bom", "routing",
                        "spool", "material_spool", "scrap_reason", "machine",
                        "printer_id", "order_type"]),
    ("Inventory", ["inventory", "adjustment", "reason_code", "transaction",
                    "stocking_policy", "negative_inventory"]),
    ("Purchasing", ["purchase", "po_", "supplier"]),
    ("Sales", ["sales_order", "customer", "margin"]),
    ("Quality", ["scrap_record", "scrap_records"]),
    ("Maintenance", ["maintenance"]),
    ("Events", ["event"]),
    ("Settings", ["company_settings", "business_hours", "timezone", "locale",
                   "business_type", "ai_config", "anthropic", "ai_provider"]),
    ("Performance", ["index", "fk_index", "performance"]),
    ("Products", ["product_image", "item_type", "product"]),
    ("UOM", ["uom", "cost_normalization", "cost_column", "cost_precision",
             "purchase_unit"]),
    ("Data Migration", ["migrate_bom", "backfill", "cleanup", "seed",
                         "sprint3_cleanup"]),
    ("Merge", ["merge"]),
]


def classify_feature(filename: str, docstring: str) -> str:
    """Classify a migration into a feature area by filename + docstring."""
    combined = (filename + " " + docstring).lower()
    for area, keywords in FEATURE_KEYWORDS:
        for kw in keywords:
            if kw in combined:
                return area
    return "Other"


# ---------------------------------------------------------------------------
# Phase definitions
# ---------------------------------------------------------------------------
# Phases are defined by the numeric prefix of the migration file.
# Hash-named migrations are placed by resolving their down_revision chain
# position into the nearest numeric phase.
PHASES = [
    (1, "Phase 1: Initial Schema", None, None),
    (2, "Phase 2: Core Features (017-031)", 17, 31),
    (3, "Phase 3: Cleanup & MRP (032-040)", 32, 40),
    (4, "Phase 4: Accounting & Customers (043-057)", 43, 57),
    (5, "Phase 5: Adjustments & Precision (058-066)", 58, 66),
]


def _numeric_prefix(filename: str) -> Optional[int]:
    """Extract leading numeric prefix like 017 from '017_add_...' ."""
    m = re.match(r"^(\d+)_", filename)
    return int(m.group(1)) if m else None


def phase_for_number(n: Optional[int]) -> int:
    """Return phase id (1-5) for a numeric prefix, or 0 if none."""
    if n is None:
        return 0
    for pid, _, lo, hi in PHASES:
        if lo is None and hi is None:
            continue
        if lo is not None and hi is not None and lo <= n <= hi:
            return pid
    # Could be initial (001) or baseline
    if n <= 2:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_migration_file(filepath: Path) -> Optional[dict]:
    """Parse a single migration .py file and extract metadata."""
    source = filepath.read_text(encoding="utf-8-sig", errors="replace")

    # --- docstring ---
    docstring = ""
    # Try extracting module docstring with ast
    try:
        tree = ast.parse(source)
        docstring = ast.get_docstring(tree) or ""
    except SyntaxError:
        pass

    # Fallback: regex on raw source (handles encoding edge cases)
    if not docstring:
        m = re.search(r'"""(.*?)"""', source, re.DOTALL)
        if m:
            docstring = m.group(1).strip()

    # --- revision / down_revision via regex (more robust than ast for tuples) ---
    revision = _extract_var(source, "revision")
    down_revision = _extract_var(source, "down_revision")

    # --- create_date from docstring or raw source ---
    create_date = None
    m = re.search(r"Create Date:\s*(\d{4}-\d{2}-\d{2})", docstring)
    if m:
        create_date = m.group(1)
    else:
        # Fallback: search raw source (handles BOM / encoding quirks)
        m = re.search(r"Create Date:\s*(\d{4}-\d{2}-\d{2})", source)
        if m:
            create_date = m.group(1)

    # --- purpose: first meaningful line of docstring ---
    purpose_lines = [l.strip() for l in docstring.split("\n") if l.strip()]
    purpose = purpose_lines[0] if purpose_lines else filepath.stem

    # Remove "Revision ID:" lines from purpose if that's the first line
    if purpose.lower().startswith("revision id"):
        purpose = purpose_lines[1] if len(purpose_lines) > 1 else filepath.stem

    # Clean up underscored filenames used as purpose text
    # e.g. "001_initial_postgres_schema" -> "Initial postgres schema"
    if "_" in purpose and " " not in purpose:
        # Strip leading numeric prefix
        cleaned = re.sub(r"^\d+_", "", purpose)
        cleaned = re.sub(r"^[0-9a-f]{12,}_", "", cleaned)
        purpose = cleaned.replace("_", " ").capitalize()

    # --- parse upgrade() body for schema operations ---
    ops = _parse_upgrade_ops(source)

    return {
        "filename": filepath.name,
        "filepath": filepath,
        "revision": revision,
        "down_revision": down_revision,
        "create_date": create_date,
        "purpose": purpose,
        "docstring": docstring,
        "ops": ops,
    }


def _extract_var(source: str, varname: str):
    """Extract a module-level variable value (str, None, or tuple of str)."""
    # Match tuple form: down_revision = ('a', 'b')
    pattern_tuple = rf"^{varname}\s*(?::\s*[^=]+=\s*|\s*=\s*)\(([^)]+)\)"
    m = re.search(pattern_tuple, source, re.MULTILINE)
    if m:
        inner = m.group(1)
        items = re.findall(r"""['"]([^'"]+)['"]""", inner)
        return tuple(items) if items else None

    # Match string form: revision = 'xxx' or revision: str = 'xxx'
    pattern_str = rf"""^{varname}\s*(?::\s*[^=]+=\s*|\s*=\s*)['"]([^'"]+)['"]"""
    m = re.search(pattern_str, source, re.MULTILINE)
    if m:
        return m.group(1)

    # Match None
    pattern_none = rf"^{varname}\s*(?::\s*[^=]+=\s*|\s*=\s*)None"
    m = re.search(pattern_none, source, re.MULTILINE)
    if m:
        return None

    return None


def _parse_upgrade_ops(source: str) -> dict:
    """Extract schema operations from upgrade() function body."""
    # Find upgrade function body
    m = re.search(r"def upgrade\(\).*?:\n(.*?)(?=\ndef |\Z)", source, re.DOTALL)
    if not m:
        return {}
    body = m.group(1)

    ops: dict = {
        "create_table": [],
        "add_column": [],
        "alter_column": [],
        "create_index": [],
        "create_foreign_key": [],
        "drop_table": [],
        "drop_column": [],
    }

    # op.create_table('name', ...)
    for match in re.finditer(r"""op\.create_table\(\s*['"]([^'"]+)['"]""", body):
        ops["create_table"].append(match.group(1))

    # op.add_column('table', sa.Column('col', ...))
    for match in re.finditer(
        r"""op\.add_column\(\s*['"]([^'"]+)['"]\s*,\s*sa\.Column\(\s*['"]([^'"]+)['"]""",
        body,
    ):
        ops["add_column"].append((match.group(1), match.group(2)))

    # op.alter_column('table', 'col', ...)
    for match in re.finditer(
        r"""op\.alter_column\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]""",
        body,
    ):
        ops["alter_column"].append((match.group(1), match.group(2)))

    # op.create_index(...)  — just grab index name or first two args
    for match in re.finditer(
        r"""op\.create_index\(\s*(?:op\.f\(\s*)?['"]([^'"]+)['"]""",
        body,
    ):
        ops["create_index"].append(match.group(1))

    # op.create_foreign_key(...)
    for match in re.finditer(
        r"""op\.create_foreign_key\(\s*['"]([^'"]+)['"]""",
        body,
    ):
        ops["create_foreign_key"].append(match.group(1))

    # op.drop_table('name')
    for match in re.finditer(r"""op\.drop_table\(\s*['"]([^'"]+)['"]""", body):
        ops["drop_table"].append(match.group(1))

    # op.drop_column('table', 'col')
    for match in re.finditer(
        r"""op\.drop_column\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]""",
        body,
    ):
        ops["drop_column"].append((match.group(1), match.group(2)))

    return ops


# ---------------------------------------------------------------------------
# Topological sort via revision chain
# ---------------------------------------------------------------------------

def build_chain(migrations: list[dict]) -> list[dict]:
    """Return migrations in dependency order (topological sort)."""
    by_rev: dict[str, dict] = {}
    for m in migrations:
        rev = m["revision"]
        if rev:
            by_rev[rev] = m

    # Build adjacency: rev -> list of revs that depend on it
    children: dict[str, list[str]] = {}
    roots: list[str] = []

    for m in migrations:
        rev = m["revision"]
        dr = m["down_revision"]
        if dr is None:
            roots.append(rev)
        elif isinstance(dr, tuple):
            # merge migration — depends on multiple parents
            for parent in dr:
                children.setdefault(parent, []).append(rev)
        else:
            children.setdefault(dr, []).append(rev)

    # BFS from roots
    ordered: list[dict] = []
    visited: set[str] = set()
    queue = list(roots)

    while queue:
        rev = queue.pop(0)
        if rev in visited or rev not in by_rev:
            continue
        visited.add(rev)
        ordered.append(by_rev[rev])
        for child in children.get(rev, []):
            # For merge nodes, only add if ALL parents visited
            child_m = by_rev.get(child)
            if child_m:
                dr = child_m["down_revision"]
                if isinstance(dr, tuple):
                    if all(p in visited for p in dr):
                        queue.append(child)
                else:
                    queue.append(child)

    # Add any remaining (disconnected) migrations
    for m in migrations:
        if m["revision"] not in visited:
            ordered.append(m)

    return ordered


# ---------------------------------------------------------------------------
# Phase assignment for hash-named migrations
# ---------------------------------------------------------------------------

def assign_phases(ordered: list[dict]) -> list[tuple[int, dict]]:
    """Assign phase numbers to each migration."""
    result: list[tuple[int, dict]] = []
    rev_to_phase: dict[str, int] = {}

    for m in ordered:
        filename = m["filename"]
        num = _numeric_prefix(filename)
        phase = phase_for_number(num)

        if phase == 0:
            # Check special cases
            if "baseline" in filename.lower() or "initial" in filename.lower():
                phase = 1
            else:
                # Inherit phase from down_revision
                dr = m["down_revision"]
                if isinstance(dr, tuple):
                    # Merge: take max phase of parents
                    phases = [rev_to_phase.get(p, 0) for p in dr]
                    phase = max(phases) if phases else 0
                elif dr and dr in rev_to_phase:
                    phase = rev_to_phase[dr]

        # If still unresolved, assign based on create_date or default to last
        if phase == 0:
            phase = 5  # fallback to latest phase

        rev_to_phase[m["revision"]] = phase
        result.append((phase, m))

    return result


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def short_rev(revision: str) -> str:
    """Return short display name for a revision."""
    # If numeric like '017', return as-is
    if re.match(r"^\d+$", revision):
        return revision
    # If has numeric prefix in the revision string
    m = re.match(r"^(\d+)_", revision)
    if m:
        return m.group(1)
    # Hash — return first 8 chars
    return revision[:12]


def format_migration_entry(m: dict) -> str:
    """Format a single migration as markdown."""
    lines = []
    lines.append(f"#### `{m['filename']}`\n")
    lines.append("**Tier**: Core")

    if m["create_date"]:
        lines.append(f"**Date**: {m['create_date']}")
    else:
        lines.append("**Date**: Initial")

    lines.append(f"**Purpose**: {m['purpose']}")

    # Revision info
    dr = m["down_revision"]
    if isinstance(dr, tuple):
        lines.append(f"**Revises**: {', '.join(dr)}")
        lines.append("**Type**: Merge migration")
    elif dr:
        lines.append(f"**Revises**: {dr}")

    ops = m.get("ops", {})
    has_ops = any(v for v in ops.values())

    if not has_ops:
        # Check if this is a no-op (stamp/merge)
        if "baseline" in m["filename"].lower() or "stamp" in m["filename"].lower():
            lines.append("\n*Baseline stamp — no schema changes.*")
        elif isinstance(m["down_revision"], tuple):
            lines.append("\n*Merge migration — no schema changes.*")
    else:
        if ops.get("create_table"):
            lines.append("\n**Creates Tables**:\n")
            for tbl in ops["create_table"]:
                desc = _table_description(tbl, m["docstring"])
                lines.append(f"- `{tbl}` - {desc}")

        if ops.get("add_column"):
            lines.append("\n**Adds Columns**:\n")
            for tbl, col in ops["add_column"]:
                lines.append(f"- `{tbl}.{col}`")

        if ops.get("alter_column"):
            lines.append("\n**Alters Columns**:\n")
            for tbl, col in ops["alter_column"]:
                lines.append(f"- `{tbl}.{col}`")

        if ops.get("create_index"):
            lines.append("\n**Creates Indexes**:\n")
            for idx in ops["create_index"]:
                lines.append(f"- `{idx}`")

        if ops.get("create_foreign_key"):
            lines.append("\n**Creates Foreign Keys**:\n")
            for fk in ops["create_foreign_key"]:
                lines.append(f"- `{fk}`")

        if ops.get("drop_table"):
            lines.append("\n**Drops Tables**:\n")
            for tbl in ops["drop_table"]:
                lines.append(f"- `{tbl}`")

        if ops.get("drop_column"):
            lines.append("\n**Drops Columns**:\n")
            for tbl, col in ops["drop_column"]:
                lines.append(f"- `{tbl}.{col}`")

    return "\n".join(lines)


def _table_description(table_name: str, docstring: str) -> str:
    """Infer a short description for a table from context."""
    descriptions = {
        "users": "User accounts",
        "products": "Product catalog",
        "inventory": "Inventory levels by location",
        "inventory_locations": "Warehouse/bin locations",
        "inventory_transactions": "Transaction audit log",
        "sales_orders": "Sales order headers",
        "sales_order_lines": "Sales order line items",
        "production_orders": "Manufacturing work orders",
        "production_order_operations": "Work order operations",
        "work_centers": "Manufacturing work centers",
        "machines": "Machine/equipment records",
        "bom_headers": "Bill of Materials headers",
        "bom_lines": "Bill of Materials line items",
        "colors": "Product color definitions",
        "company_settings": "Company configuration",
        "purchase_orders": "Purchase order headers",
        "purchase_order_lines": "Purchase order line items",
        "material_spools": "Individual spool records with weight tracking",
        "spool_consumption_records": "Spool usage/consumption log",
        "maintenance_logs": "Equipment maintenance records",
        "events": "System event records",
        "event_types": "Event type definitions",
        "gl_accounts": "Chart of Accounts",
        "gl_fiscal_periods": "Fiscal period tracking",
        "gl_journal_entries": "Journal entry headers",
        "gl_journal_entry_lines": "Journal entry debit/credit lines",
        "scrap_records": "Scrap/waste tracking records",
        "scrap_reasons": "Scrap reason codes",
        "routing_operation_materials": "Materials consumed per routing operation",
        "production_order_materials": "Production order material tracking",
        "po_documents": "Purchase order document attachments",
        "adjustment_reasons": "Inventory adjustment reason codes",
        "tax_rates": "Tax rate definitions",
        "customers": "Customer records",
    }
    if table_name in descriptions:
        return descriptions[table_name]
    # Generate from table name
    return table_name.replace("_", " ").title()


def _dep_tree_label(m: dict) -> str:
    """Human-readable label for the dependency tree."""
    rev = m["revision"]
    filename = m["filename"]
    # Numeric-only revisions: show as NNN_description
    num = _numeric_prefix(filename)
    if num is not None:
        stem = filename.replace(".py", "")
        return stem
    if rev.startswith("baseline"):
        return rev
    # Hash revisions: show hash (description)
    stem = filename.replace(".py", "")
    # Remove hash prefix from stem for cleaner display
    desc = re.sub(r"^[0-9a-f]+_", "", stem)
    return f"{rev[:12]} ({desc})"


def build_dependency_tree(ordered: list[dict]) -> str:
    """Build a text-based dependency tree."""
    lines = ["```"]
    for i, m in enumerate(ordered):
        dr = m["down_revision"]
        label = _dep_tree_label(m)

        if isinstance(dr, tuple):
            parents = ", ".join(str(p) for p in dr)
            lines.append(f"  {parents}")
            lines.append(f"    \\ /")
            lines.append(f"     {label}  [merge]")
        elif i == 0:
            lines.append(f"{label}")
        else:
            lines.append(f"    |")
            lines.append(f"{label}")

    lines.append("```")
    return "\n".join(lines)


def build_feature_table(phased: list[tuple[int, dict]]) -> str:
    """Build the feature-area summary table."""
    area_map: dict[str, list[str]] = {}
    for _, m in phased:
        area = classify_feature(m["filename"], m["docstring"])
        short = short_rev(m["revision"])
        area_map.setdefault(area, []).append(short)

    lines = [
        "| Area | Count | Migrations |",
        "|------|-------|------------|",
    ]
    for area, revs in area_map.items():
        rev_str = ", ".join(revs)
        lines.append(f"| {area} | {len(revs)} | {rev_str} |")

    return "\n".join(lines)


def generate_markdown(ordered: list[dict], phased: list[tuple[int, dict]]) -> str:
    """Generate the full MIGRATIONS-LOG.md content."""
    version = "unknown"
    if VERSION_FILE.exists():
        version = VERSION_FILE.read_text().strip()

    today = date.today().isoformat()
    total = len(ordered)

    parts = []

    # Header
    parts.append("""<!-- AUTO-GENERATED — Do not edit manually. Regenerate: cd backend && python scripts/generate_migrations_log.py -->

# FilaOps Migrations Log

> Chronological record of all database migrations with feature mapping.
> Generated for AI consumption and developer reference.
>
> This document covers **Core (Open Source)** migrations only.

## Overview

| Metric | Count |
| ------ | ----- |
| **Total Migrations** | {total} |
| **Database** | PostgreSQL |
| **Tool** | Alembic |

---

## Migration Categories

### By Feature Area

{feature_table}

---

## Chronological Migration List
""".format(total=total, feature_table=build_feature_table(phased)))

    # Group by phase
    phase_groups: dict[int, list[dict]] = {}
    for pid, m in phased:
        phase_groups.setdefault(pid, []).append(m)

    for pid, title, _, _ in PHASES:
        migs = phase_groups.get(pid, [])
        if not migs:
            continue
        parts.append(f"### {title}\n")
        for m in migs:
            parts.append(format_migration_entry(m))
            parts.append("\n---\n")

    # Dependency tree
    parts.append("## Migration Dependencies\n")
    parts.append(build_dependency_tree(ordered))

    # Running migrations
    parts.append("""

---

## Running Migrations

```bash
# Upgrade to latest
cd backend
alembic upgrade head

# Downgrade one revision
alembic downgrade -1

# Show current revision
alembic current

# Show migration history
alembic history --verbose
```

---

*Last updated: {today}*
*Generated for FilaOps Core (Open Source)*
""".format(today=today))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not VERSIONS_DIR.is_dir():
        print(f"ERROR: Migrations directory not found: {VERSIONS_DIR}")
        return

    # Scan all .py migration files (skip __pycache__)
    py_files = sorted(
        f for f in VERSIONS_DIR.glob("*.py")
        if f.name != "__init__.py"
    )

    print(f"Scanning {len(py_files)} migration files in {VERSIONS_DIR}")

    migrations = []
    for f in py_files:
        m = parse_migration_file(f)
        if m and m["revision"]:
            migrations.append(m)
        else:
            print(f"  WARNING: Could not parse revision from {f.name}")

    print(f"Parsed {len(migrations)} migrations")

    # Build dependency chain
    ordered = build_chain(migrations)
    print(f"Ordered {len(ordered)} migrations by dependency chain")

    # Assign phases
    phased = assign_phases(ordered)

    # Generate markdown
    md = generate_markdown(ordered, phased)

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(md, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH} ({len(md)} bytes)")


if __name__ == "__main__":
    main()
