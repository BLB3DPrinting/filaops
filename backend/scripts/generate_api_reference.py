#!/usr/bin/env python3
"""
Generate docs/API-REFERENCE.md from the FilaOps Core codebase.

Reads router registrations from __init__.py files and uses AST to extract
route decorators, HTTP methods, paths, docstrings, and auth levels from
each endpoint file.

Run from backend/:
    python scripts/generate_api_reference.py
"""

import ast
import os
import re
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent          # backend/
ENDPOINTS_DIR = BACKEND_DIR / "app" / "api" / "v1" / "endpoints"
ADMIN_DIR = ENDPOINTS_DIR / "admin"
V1_INIT = BACKEND_DIR / "app" / "api" / "v1" / "__init__.py"
ADMIN_INIT = ADMIN_DIR / "__init__.py"
OUTPUT_FILE = BACKEND_DIR.parent / "docs" / "API-REFERENCE.md"

# ---------------------------------------------------------------------------
# Router registration order & prefixes (parsed from __init__.py manually is
# fragile; instead we encode the authoritative map here so the script is
# deterministic and matches the spec).
# ---------------------------------------------------------------------------

# (module_name, prefix_from_init_or_None)
# None means __init__.py calls `include_router(mod.router)` with no prefix,
# so the router's own prefix (from APIRouter(prefix=...)) is used.
ROUTER_ORDER: list[tuple[str, str | None]] = [
    ("auth",              None),
    ("setup",             None),
    ("sales_orders",      None),
    ("quotes",            None),
    ("products",          "/products"),
    ("items",             "/items"),
    ("production_orders", "/production-orders"),
    ("operation_status",  "/production-orders"),
    ("inventory",         "/inventory"),
    ("materials",         "/materials"),
    ("vendors",           "/vendors"),
    ("purchase_orders",   "/purchase-orders"),
    ("po_documents",      "/purchase-orders"),
    ("low_stock",         "/purchase-orders"),
    ("vendor_items",      "/purchase-orders"),
    ("work_centers",      "/work-centers"),
    ("resources",         "/resources"),
    ("routings",          "/routings"),
    ("mrp",               None),
    ("scheduling",        "/scheduling"),
    ("settings",          None),
    ("tax_rates",         None),
    ("payments",          None),
    ("accounting",        "/accounting"),
    ("printers",          "/printers"),
    ("system",            None),
    ("security",          None),
    ("spools",            None),
    ("traceability",      "/traceability"),
    ("maintenance",       "/maintenance"),
    ("command_center",    "/command-center"),
]

# Admin sub-module order (from admin/__init__.py)
ADMIN_ORDER: list[str] = [
    "users",
    "customers",
    "bom",
    "dashboard",
    "analytics",
    "fulfillment_queue",
    "fulfillment_shipping",
    "audit",
    "accounting",
    "traceability",
    "inventory_transactions",
    "export",
    "data_import",
    "orders",
    "uom",
    "locations",
    "system",
    "uploads",
]

# Admin sub-module prefixes from admin/__init__.py
# uploads gets prefix="/uploads" in __init__.py; the rest rely on their own
# APIRouter(prefix=...).
ADMIN_INIT_PREFIXES: dict[str, str | None] = {
    "uploads": "/uploads",
}

# Modules that share an __init__.py prefix and should be grouped together.
# Key = display prefix, value = list of modules in that group (first is the
# "primary" whose name is used for the section heading).
SHARED_PREFIX_GROUPS: dict[str, list[str]] = {
    "/production-orders": ["production_orders", "operation_status"],
    "/purchase-orders":   ["purchase_orders", "po_documents", "low_stock", "vendor_items"],
}

# Inverse lookup: module -> group prefix (if any)
_MODULE_TO_GROUP: dict[str, str] = {}
for _pfx, _mods in SHARED_PREFIX_GROUPS.items():
    for _m in _mods:
        _MODULE_TO_GROUP[_m] = _pfx


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

AUTH_DEPS = {
    "get_current_admin_user": "ADMIN",
    "get_current_staff_user": "STAFF",
    "get_current_user":       "CUSTOMER",
}


def _extract_router_prefix(tree: ast.Module) -> str:
    """Return the prefix= passed to APIRouter(...) in a module, or ''."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "router":
                    if isinstance(node.value, ast.Call):
                        for kw in node.value.keywords:
                            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                                return kw.value.value
    return ""


def _humanize(name: str) -> str:
    """Convert function name to human-readable description."""
    name = name.strip("_")
    words = name.replace("_", " ").strip()
    return words.capitalize() if words else name


def _detect_auth(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Detect auth level from function parameters and body."""
    # Check Depends(...) in parameters
    for arg in func_node.args.args:
        if arg.annotation is not None:
            # might be wrapped in Annotated — skip complex forms
            pass
    for default in func_node.args.defaults + func_node.args.kw_defaults:
        if default is None:
            continue
        dep_name = _depends_name(default)
        if dep_name and dep_name in AUTH_DEPS:
            return AUTH_DEPS[dep_name]

    # Check keyword-only defaults too
    # Already covered above via kw_defaults

    # Fallback: scan full argument list annotations for Depends
    # (handles `current_user: User = Depends(get_current_admin_user)`)
    # — already handled by defaults above, but also check annotations
    # that use Annotated[..., Depends(...)]:
    for arg in func_node.args.args + func_node.args.kwonlyargs:
        anno = arg.annotation
        if anno is None:
            continue
        dep = _depends_from_annotation(anno)
        if dep and dep in AUTH_DEPS:
            return AUTH_DEPS[dep]

    # Body-level check: `if not current_user.is_admin` etc.
    for node in ast.walk(func_node):
        if isinstance(node, ast.Attribute) and node.attr in ("is_admin",):
            return "ADMIN"

    return "PUBLIC"


def _depends_name(node: ast.expr) -> str | None:
    """If *node* is ``Depends(some_func)``, return ``'some_func'``."""
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "Depends" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Name):
                return first.id
            if isinstance(first, ast.Attribute):
                return first.attr
    return None


def _depends_from_annotation(node: ast.expr) -> str | None:
    """Handle Annotated[Type, Depends(func)]."""
    if isinstance(node, ast.Subscript):
        # Annotated[X, Depends(...)]
        if isinstance(node.slice, ast.Tuple):
            for elt in node.slice.elts:
                dep = _depends_name(elt)
                if dep:
                    return dep
    return None


def _extract_path(decorator: ast.Call) -> str:
    """Extract the path string from a route decorator call."""
    if decorator.args:
        first = decorator.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    # Check for path= keyword
    for kw in decorator.keywords:
        if kw.arg == "path" and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return "/"


def extract_routes(filepath: Path, init_prefix: str | None) -> list[dict]:
    """Extract all route definitions from an endpoint file.

    Returns a list of dicts with keys:
        method, path, name, description, auth
    """
    source = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    router_prefix = _extract_router_prefix(tree)

    # Effective prefix: init_prefix overrides router_prefix only when the
    # __init__.py supplies one.  But the router's *own* prefix still applies
    # on top when __init__.py also supplies a prefix — wait, no.  FastAPI's
    # include_router(prefix=X) *prepends* X to the router's own prefix.
    # So effective = (init_prefix or "") + router_prefix + route_path.
    if init_prefix is not None:
        effective_prefix = init_prefix + router_prefix
    else:
        effective_prefix = router_prefix

    routes: list[dict] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            func = deco.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr not in HTTP_METHODS:
                continue
            # Verify it's on `router`
            if isinstance(func.value, ast.Name) and func.value.id == "router":
                method = func.attr.upper()
                route_path = _extract_path(deco)
                full_path = effective_prefix + route_path
                # Normalise double slashes
                full_path = re.sub(r"//+", "/", full_path)

                # Description from docstring
                docstring = ast.get_docstring(node) or ""
                if docstring:
                    description = docstring.strip().split("\n")[0]
                else:
                    description = _humanize(node.name)

                auth = _detect_auth(node)

                routes.append({
                    "method": method,
                    "path": full_path,
                    "name": node.name,
                    "description": description,
                    "auth": auth,
                })
                break  # one route per decorator match

    return routes


# ---------------------------------------------------------------------------
# Grouping logic
# ---------------------------------------------------------------------------

def _module_display_name(module_name: str) -> str:
    """Human-readable section title from module name."""
    return module_name.replace("_", " ").title()


def _module_to_filepath(module_name: str, admin: bool = False) -> Path:
    base = ADMIN_DIR if admin else ENDPOINTS_DIR
    return base / f"{module_name}.py"


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def generate():
    sections: list[str] = []       # Markdown section strings
    all_routes: list[dict] = []    # Flat list for metrics
    section_num = 0

    # Track which modules have been emitted (for shared-prefix grouping)
    emitted: set[str] = set()

    # ----- Non-admin routers -----
    for module_name, init_prefix in ROUTER_ORDER:
        if module_name in emitted:
            continue

        group_prefix = _MODULE_TO_GROUP.get(module_name)
        if group_prefix:
            # Emit the whole group at once
            group_modules = SHARED_PREFIX_GROUPS[group_prefix]
            group_routes: list[dict] = []
            file_names: list[str] = []
            for gm in group_modules:
                fp = _module_to_filepath(gm)
                if fp.exists():
                    gr = extract_routes(fp, init_prefix)
                    group_routes.extend(gr)
                    file_names.append(f"`endpoints/{gm}.py`")
                emitted.add(gm)
            if not group_routes:
                continue
            all_routes.extend(group_routes)
            section_num += 1
            title = _module_display_name(group_modules[0])
            sec = _format_section(
                section_num, title, group_prefix,
                ", ".join(file_names), group_routes,
            )
            sections.append(sec)
        else:
            fp = _module_to_filepath(module_name)
            if not fp.exists():
                continue
            routes = extract_routes(fp, init_prefix)
            if not routes:
                emitted.add(module_name)
                continue
            all_routes.extend(routes)
            emitted.add(module_name)
            section_num += 1
            # Determine display prefix from first route
            display_prefix = init_prefix if init_prefix else ""
            if not display_prefix and routes:
                # Infer from first route path
                first_path = routes[0]["path"]
                parts = first_path.strip("/").split("/")
                if parts:
                    display_prefix = "/" + parts[0]
            sec = _format_section(
                section_num,
                _module_display_name(module_name),
                display_prefix,
                f"`endpoints/{module_name}.py`",
                routes,
            )
            sections.append(sec)

    # ----- Admin router -----
    section_num += 1
    admin_section_num = section_num
    admin_header = f"## {admin_section_num}. Admin (`/admin`)\n"
    admin_subsections: list[str] = []
    sub_idx = 0

    for admin_mod in ADMIN_ORDER:
        fp = _module_to_filepath(admin_mod, admin=True)
        if not fp.exists():
            continue
        admin_init_pfx = ADMIN_INIT_PREFIXES.get(admin_mod)
        # Admin routes get /admin prepended by __init__.py, then the sub-module's
        # own prefix (or the one from admin/__init__.py).
        routes = extract_routes(fp, "/admin" if admin_init_pfx is None else f"/admin{admin_init_pfx}")
        if not routes:
            continue
        all_routes.extend(routes)
        sub_idx += 1
        # Derive display prefix from first route
        first_path = routes[0]["path"]
        path_parts = first_path.strip("/").split("/")
        if len(path_parts) >= 2:
            display_prefix = "/" + "/".join(path_parts[:2])
        else:
            display_prefix = first_path
        sub_title = _module_display_name(admin_mod)
        sub = _format_admin_subsection(
            admin_section_num, sub_idx, sub_title, display_prefix,
            f"`endpoints/admin/{admin_mod}.py`", routes,
        )
        admin_subsections.append(sub)

    sections.append(admin_header + "\n".join(admin_subsections))

    # ----- Metrics -----
    total = len(all_routes)
    method_counts: dict[str, int] = {}
    for r in all_routes:
        m = r["method"]
        method_counts[m] = method_counts.get(m, 0) + 1

    # Count unique endpoint files
    router_files = set()
    for mod, _ in ROUTER_ORDER:
        fp = _module_to_filepath(mod)
        if fp.exists():
            router_files.add(str(fp))
    for mod in ADMIN_ORDER:
        fp = _module_to_filepath(mod, admin=True)
        if fp.exists():
            router_files.add(str(fp))

    num_router_files = len(router_files)
    num_top_groups = section_num  # includes admin
    num_admin_subs = sub_idx

    gets = method_counts.get("GET", 0)
    posts = method_counts.get("POST", 0)
    puts = method_counts.get("PUT", 0) + method_counts.get("PATCH", 0)
    deletes = method_counts.get("DELETE", 0)

    # ----- Assemble document -----
    doc = f"""\
<!-- AUTO-GENERATED — Do not edit manually. Regenerate: cd backend && python scripts/generate_api_reference.py -->

# FilaOps API Reference

> Complete API endpoint documentation for FilaOps Core ERP system.
> Generated for AI consumption and developer reference.
> This document covers **Core (Open Source)** API endpoints only.

## Overview

| Metric | Count |
| ------ | ----- |
| **Total Endpoints** | ~{total} |
| **Router Files** | {num_router_files} |
| **Router Groups** | {num_top_groups} (including {num_admin_subs} admin sub-modules) |
| **Base Path** | `/api/v1/` |

### HTTP Method Distribution

- **GET**: ~{gets} endpoints (read/query operations)
- **POST**: ~{posts} endpoints (create/execute operations)
- **PUT/PATCH**: ~{puts} endpoints (update operations)
- **DELETE**: ~{deletes} endpoints (delete operations)

---

## Authentication

All endpoints except those marked `PUBLIC` require JWT Bearer token authentication.

```http
Authorization: Bearer <access_token>
```

### Auth Levels

- **PUBLIC**: No authentication required
- **CUSTOMER**: Requires valid JWT (any user type)
- **STAFF**: Requires `account_type` in ['admin', 'operator']
- **ADMIN**: Requires `account_type` = 'admin'

---

"""

    doc += "\n---\n\n".join(sections)

    doc += """

---

## Pagination

Most list endpoints return paginated responses:

```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 50,
  "pages": 2
}
```

---

## Filtering

Most list endpoints support filtering via query parameters:

- `status` - Filter by status
- `search` - Text search
- `date_from`, `date_to` - Date range
- `product_id`, `customer_id`, etc. - Foreign key filters

---

## Versioning

Current API version: `v1`

All endpoints are prefixed with `/api/v1/`

---

"""

    doc += f"*Last updated: {date.today().isoformat()}*\n"
    doc += "*Generated for FilaOps Core*\n"

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(doc, encoding="utf-8")
    print(f"Generated {OUTPUT_FILE} — {total} endpoints across {num_router_files} files")


# ---------------------------------------------------------------------------
# Markdown formatters
# ---------------------------------------------------------------------------

def _format_section(num: int, title: str, prefix: str, file_ref: str,
                    routes: list[dict]) -> str:
    lines = [
        f"## {num}. {title} (`{prefix}`)\n",
        f"**Tier**: Core",
        f"**File**: {file_ref}",
        f"**Endpoints**: {len(routes)}\n",
        "| Method | Path | Description | Auth |",
        "| ------ | ---- | ----------- | ---- |",
    ]
    for r in routes:
        lines.append(
            f"| {r['method']} | `{r['path']}` | {r['description']} | {r['auth']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _format_admin_subsection(parent_num: int, sub_num: int, title: str,
                              prefix: str, file_ref: str,
                              routes: list[dict]) -> str:
    lines = [
        f"### {parent_num}.{sub_num}. {title} (`{prefix}`)\n",
        f"**Tier**: Core",
        f"**File**: {file_ref}",
        f"**Endpoints**: {len(routes)}\n",
        "| Method | Path | Description | Auth |",
        "| ------ | ---- | ----------- | ---- |",
    ]
    for r in routes:
        lines.append(
            f"| {r['method']} | `{r['path']}` | {r['description']} | {r['auth']} |"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    generate()
