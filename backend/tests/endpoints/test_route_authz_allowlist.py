"""SEC-410: every Core route needs a staff or admin account unless reviewed.

Anyone can self-register a customer account, so a plain login
(``get_current_user``) is not an authorization check. This test walks every
route the app serves and fails if a route does not depend, directly, through
a router-level dependency or through a nested dependency, on
``get_current_staff_user`` or ``get_current_admin_user``, unless the route is
in ``ALLOWLIST`` below with a category and a one-line reason.

Adding a route? Gate it with ``Depends(get_current_staff_user)`` (or the admin
dependency), ideally on the module's ``APIRouter(dependencies=[...])``. Only
add an ALLOWLIST entry if the route must be reachable by anonymous callers
(``public``), by any logged-in user and scoped to their own records
(``customer``), or by a machine caller that authenticates some other way
(``service``), and say why in one line.

The same enumeration drives the behaviour sweep in
``test_customer_route_sweep.py`` (customer token -> 403, anonymous -> 401).

PRO routes (module ``filaops_pro``) are skipped: PRO's own tests own them.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple

import pytest
from fastapi import APIRouter, Depends, FastAPI, WebSocket
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles

from app.api.v1.deps import (
    get_current_admin_user,
    get_current_staff_user,
    get_current_user,
)

ROLE_GATES = (get_current_staff_user, get_current_admin_user)
CATEGORIES = ("public", "customer", "service")

# Fewer /api/v1 routes than this means the walker lost routes (for example a
# FastAPI upgrade changed how included routers are stored, or a router module
# stopped being included). 528 are served in every environment, plus the four
# /api/v1/test routes when test endpoints are enabled (532 in this suite).
# Raise this when a large router is added.
MIN_API_ROUTES = 500


class Entry(NamedTuple):
    category: str
    reason: str
    # Exists only in some configurations (docs off in production, the test
    # router only when test_endpoints_enabled(), SPA shells only when a *_DIST
    # is set), so it is exempt from the stale-entry check.
    conditional: bool = False


# (METHOD, path exactly as FastAPI reports it) -> Entry. MOUNT entries are
# allowed only when the mounted app is a StaticFiles instance.
ALLOWLIST: dict[tuple[str, str], Entry] = {
    # --- app root and API docs --------------------------------------------
    ("GET", "/"): Entry("public", "API status JSON or the SPA index.html; no data"),
    ("GET", "/health"): Entry("public", "Liveness/readiness probe; returns version and DB up/down"),
    ("GET", "/docs"): Entry("public", "Swagger UI; disabled when ENVIRONMENT=production", True),
    ("GET", "/docs/oauth2-redirect"): Entry("public", "Swagger OAuth redirect; disabled in production", True),
    ("GET", "/openapi.json"): Entry("public", "OpenAPI schema; disabled in production", True),
    ("GET", "/redoc"): Entry("public", "ReDoc UI; disabled in production", True),
    # --- authentication (anonymous by design) ------------------------------
    ("POST", "/api/v1/auth/login"): Entry("public", "Credential login; issues tokens only for valid credentials"),
    ("POST", "/api/v1/auth/logout"): Entry("public", "Revokes only the refresh token in the caller's own cookie"),
    ("POST", "/api/v1/auth/refresh"): Entry("public", "Rotates the caller's own valid, unrevoked refresh token"),
    ("POST", "/api/v1/auth/register"): Entry(
        "public", "Self-registration; always account_type=customer; off unless ENABLE_PUBLIC_QUOTER"),
    ("POST", "/api/v1/auth/portal/register"): Entry(
        "public", "Quoter self-signup; always account_type=customer; off unless ENABLE_PUBLIC_QUOTER"),
    ("POST", "/api/v1/auth/portal/login"): Entry("public", "Quoter customer login; refuses non-customer accounts"),
    ("POST", "/api/v1/auth/password-reset/request"): Entry(
        "public", "Same response for every email; token is never returned"),
    ("POST", "/api/v1/auth/password-reset/approve"): Entry(
        "public", "Authorised by the 256-bit approval token emailed to the admin"),
    ("POST", "/api/v1/auth/password-reset/deny"): Entry("public", "Authorised by the emailed approval token"),
    ("GET", "/api/v1/auth/password-reset/status/{token}"): Entry(
        "public", "Needs the unguessable reset token; returns status only"),
    ("POST", "/api/v1/auth/password-reset/complete"): Entry(
        "public", "Needs an admin-approved reset token inside the approval window"),
    # --- first run ---------------------------------------------------------
    ("GET", "/api/v1/setup/status"): Entry(
        "public", "Reveals only whether any user exists (login/onboarding need it)"),
    ("POST", "/api/v1/setup/initial-admin"): Entry("public", "First-run only; refuses once any user exists"),
    # --- system ------------------------------------------------------------
    ("GET", "/api/v1/system/version"): Entry("public", "Version string shown before login"),
    ("GET", "/api/v1/system/info"): Entry("public", "Tier and feature flags the SPA needs before login"),
    ("GET", "/api/v1/system/health"): Entry("public", "Health probe"),
    ("GET", "/api/v1/settings/company/logo"): Entry(
        "public", "Logo image for PDFs and the PRO B2B portal (buyers load it anonymously)"),
    # --- customer: any logged-in user, scoped to their own records ----------
    # The Quoter and PRO call these with customer tokens; a staff gate here
    # breaks them (test_customer_routes_stay_customer_reachable).
    ("GET", "/api/v1/auth/me"): Entry("customer", "Returns only the caller's own profile"),
    ("POST", "/api/v1/quotes/portal"): Entry(
        "customer", "Public quoter upload; quote is created with user_id=customer_id=caller"),
    ("POST", "/api/v1/quotes/portal/{quote_id}/accept"): Entry(
        "customer",
        "Owner only, and only quotes the owner created (user_id); origin, status, price, tax and "
        "print spec checked server-side (SEC-412)"),
    ("POST", "/api/v1/quotes/portal/{quote_id}/checkout"): Entry(
        "customer", "Owner only (_portal_quote_or_404); PRO checkout charges the stored total"),
    ("GET", "/api/v1/quotes/{quote_id}/archive"): Entry(
        "customer", "Owner or staff (_authorize_quote_archive_access); admin_notes stripped for non-staff"),
    ("GET", "/api/v1/quotes/{quote_id}/files"): Entry(
        "customer", "Owner or staff (_authorize_quote_archive_access)"),
    ("GET", "/api/v1/quotes/{quote_id}/files/{file_id}/download"): Entry(
        "customer", "Owner or staff; file must belong to that quote"),
    # --- service: test harness only ----------------------------------------
    ("GET", "/api/v1/test/scenarios"): Entry(
        "service", "Mounted only when test_endpoints_enabled(); never in production", True),
    ("POST", "/api/v1/test/seed"): Entry("service", "Test-only mount plus require_test_mode", True),
    ("POST", "/api/v1/test/cleanup"): Entry(
        "service", "Test-only mount plus require_test_mode and require_data_wipe_allowed", True),
    ("GET", "/api/v1/test/health"): Entry("service", "Test-only mount; returns the ENVIRONMENT name", True),
    # --- optional SPA shells (registered only when *_DIST is configured) ----
    ("GET", "/portal-admin"): Entry("public", "Static SPA shell index.html (PORTAL_ADMIN_DIST)", True),
    ("GET", "/portal"): Entry("public", "Static SPA shell index.html (PORTAL_DIST)", True),
    ("GET", "/quote"): Entry("public", "Static SPA shell index.html (QUOTER_DIST)", True),
    # --- static mounts (StaticFiles only) -----------------------------------
    ("MOUNT", "/static"): Entry(
        "public",
        "StaticFiles: product images (public by design); PO docs, QC photos and quote uploads are "
        "stored outside it"),
    ("MOUNT", "/static/uploads/products"): Entry(
        "public",
        "Product images (same files /static served before they moved to the "
        "uploads volume); MultiDirStaticFiles = StaticFiles over two dirs",
        True,
    ),
    ("MOUNT", "/portal-admin"): Entry("public", "StaticFiles SPA bundle (PORTAL_ADMIN_DIST)", True),
    ("MOUNT", "/portal"): Entry("public", "StaticFiles SPA bundle (PORTAL_DIST)", True),
    ("MOUNT", "/quote"): Entry("public", "StaticFiles SPA bundle (QUOTER_DIST)", True),
    ("MOUNT", "/"): Entry(
        "public", "Catch-all StaticFiles SPA bundle (FRONTEND_DIST); 404 for /api and /static", True),
}


class RouteInfo(NamedTuple):
    method: str
    path: str
    endpoint: str
    dependant: object
    kind: str  # "api", "route", "websocket", "mount" or "unknown"
    mount_app: object = None


# ----------------------------------------------------------------------------
# Enumeration and dependency walk (shared with test_customer_route_sweep.py)
# ----------------------------------------------------------------------------

def _iter_route_items(app: FastAPI) -> Iterable[object]:
    """Flatten app.routes, router-level dependencies included.

    FastAPI 0.13x keeps included routers lazy; iter_route_contexts yields one
    context per served route whose ``dependant`` already merges the
    include-level and router-level dependencies. Older FastAPI copies every
    route into app.routes with those dependencies merged, so app.routes is
    enough there.
    """
    try:
        from fastapi.routing import iter_route_contexts  # type: ignore[attr-defined]
    except ImportError:  # pragma: no cover - older FastAPI
        yield from app.routes
        return
    yield from iter_route_contexts(app.routes)


def _endpoint_name(endpoint) -> str:
    if endpoint is None:
        return "?"
    return f"{getattr(endpoint, '__module__', '?')}.{getattr(endpoint, '__qualname__', repr(endpoint))}"


def collect_routes(app: FastAPI) -> list[RouteInfo]:
    """Every (method, path) the app serves, one RouteInfo per method."""
    out: list[RouteInfo] = []
    for item in _iter_route_items(app):
        original = getattr(item, "original_route", item)
        ctx = getattr(item, "_route_context", None)
        eff = getattr(ctx, "starlette_route", None) or item
        if isinstance(original, APIRoute):
            methods = sorted(m for m in (item.methods or []) if m != "HEAD") or ["GET"]
            for method in methods:
                out.append(RouteInfo(method, item.path, _endpoint_name(item.endpoint),
                                     getattr(item, "dependant", None), "api"))
        elif isinstance(original, (APIWebSocketRoute, WebSocketRoute)):
            out.append(RouteInfo("WEBSOCKET", getattr(eff, "path", original.path),
                                 _endpoint_name(getattr(eff, "endpoint", None)),
                                 getattr(eff, "dependant", None), "websocket"))
        elif isinstance(original, Mount):
            # Starlette stores Mount("/") as path "".
            path = getattr(eff, "path", original.path) or "/"
            out.append(RouteInfo("MOUNT", path, "mount", None, "mount", getattr(original, "app", None)))
        elif isinstance(original, Route):
            methods = sorted(m for m in (getattr(eff, "methods", None) or ["GET"]) if m != "HEAD") or ["GET"]
            for method in methods:
                out.append(RouteInfo(method, getattr(eff, "path", original.path),
                                     _endpoint_name(getattr(eff, "endpoint", None)), None, "route"))
        else:  # unknown route type (Host, custom BaseRoute): must be reviewed
            out.append(RouteInfo("?", str(getattr(item, "path", "?")), type(original).__name__, None, "unknown"))
    return out


def depends_on(dependant, targets) -> bool:
    """True if the dependency tree (router-, route- and sub-dependencies) reaches a target."""
    seen: set[int] = set()
    stack = list(getattr(dependant, "dependencies", None) or [])
    while stack:
        sub = stack.pop()
        if id(sub) in seen:
            continue
        seen.add(id(sub))
        if getattr(sub, "call", None) in targets:
            return True
        stack.extend(getattr(sub, "dependencies", None) or [])
    return False


def is_role_gated(route: RouteInfo) -> bool:
    return route.kind == "api" and depends_on(route.dependant, ROLE_GATES)


def is_core_route(route: RouteInfo) -> bool:
    return not route.endpoint.startswith("filaops_pro")


def ungated_routes(app: FastAPI, allowlist: dict[tuple[str, str], Entry] = ALLOWLIST) -> list[str]:
    """Human-readable list of routes that are neither role-gated nor allowlisted."""
    problems = []
    for r in collect_routes(app):
        if not is_core_route(r):
            continue
        if r.kind == "mount":
            if ("MOUNT", r.path) in allowlist and isinstance(r.mount_app, StaticFiles):
                continue
            problems.append(f"MOUNT {r.path!r} ({type(r.mount_app).__name__}) is not a reviewed static mount")
            continue
        if is_role_gated(r):
            continue
        if (r.method, r.path) in allowlist:
            continue
        problems.append(f"{r.method} {r.path} -> {r.endpoint}")
    return sorted(problems)


# ----------------------------------------------------------------------------
# Tests against the real app
# ----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def core_routes():
    from app.main import app
    return [r for r in collect_routes(app) if is_core_route(r)]


@pytest.fixture(scope="module")
def core_app():
    from app.main import app
    return app


def test_route_enumeration_is_not_empty(core_routes):
    api = [r for r in core_routes if r.kind == "api" and r.path.startswith("/api/v1/")]
    assert len(api) >= MIN_API_ROUTES, (
        f"only {len(api)} /api/v1 routes enumerated (expected at least {MIN_API_ROUTES}); "
        "the route walker is broken, so the authorization checks below prove nothing"
    )


def test_every_route_is_staff_gated_or_allowlisted(core_app):
    problems = ungated_routes(core_app)
    assert not problems, (
        f"{len(problems)} route(s) reachable without a staff or admin dependency and not in ALLOWLIST:\n  "
        + "\n  ".join(problems)
        + "\nGate them with Depends(get_current_staff_user) / Depends(get_current_admin_user), "
        "or add a reviewed ALLOWLIST entry with a one-line reason."
    )


def test_allowlist_has_no_stale_entries(core_routes):
    present = {(r.method, r.path) for r in core_routes}
    stale = sorted(k for k, entry in ALLOWLIST.items() if k not in present and not entry.conditional)
    assert not stale, f"ALLOWLIST entries that match no route (remove them): {stale}"


def test_allowlist_entries_are_categorised():
    for key, entry in ALLOWLIST.items():
        assert entry.category in CATEGORIES, key
        assert entry.reason.strip(), key
        if key[0] == "MOUNT":
            assert entry.category == "public", key


def test_public_routes_stay_anonymous(core_routes):
    """Public entries must not require a login (PRO's B2B portal loads the logo anonymously)."""
    needs_login = sorted(
        (r.method, r.path) for r in core_routes
        if (r.method, r.path) in ALLOWLIST and ALLOWLIST[(r.method, r.path)].category == "public"
        and depends_on(r.dependant, (get_current_user, *ROLE_GATES))
    )
    assert not needs_login, f"public ALLOWLIST routes that now require a login: {needs_login}"


def test_customer_routes_stay_customer_reachable(core_routes):
    """The Quoter and PRO call these with a customer token; a staff gate breaks them."""
    by_key = {(r.method, r.path): r for r in core_routes if r.kind == "api"}
    problems = []
    for key, entry in ALLOWLIST.items():
        if entry.category != "customer":
            continue
        route = by_key.get(key)
        if route is None:
            problems.append(f"{key} is no longer served")
        elif not depends_on(route.dependant, (get_current_user,)):
            problems.append(f"{key} must require login (Depends(get_current_user))")
        elif depends_on(route.dependant, ROLE_GATES):
            problems.append(f"{key} has a staff/admin gate; customer tokens can no longer reach it")
    assert not problems, "customer ALLOWLIST routes broken:\n  " + "\n  ".join(problems)


# ----------------------------------------------------------------------------
# The checker itself must fail for a new, unlisted route
# ----------------------------------------------------------------------------

def _mini_app() -> FastAPI:
    """A tiny app with one of every shape the checker must get right."""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    staff = APIRouter(dependencies=[Depends(get_current_staff_user)])

    @staff.get("/widgets")
    async def gated_by_router():  # pragma: no cover - never called
        return {}

    open_router = APIRouter()

    @open_router.get("/widgets/{widget_id}")
    async def login_only(user=Depends(get_current_user)):  # pragma: no cover
        return {}

    @open_router.post("/widgets/import")
    async def anonymous():  # pragma: no cover
        return {}

    async def needs_admin(user=Depends(get_current_admin_user)):  # pragma: no cover
        return user

    @open_router.delete("/widgets/{widget_id}")
    async def gated_through_nested_dependency(user=Depends(needs_admin)):  # pragma: no cover
        return {}

    @open_router.websocket("/widgets/live")
    async def websocket_feed(websocket: WebSocket):  # pragma: no cover
        return None

    included_with_gate = APIRouter()

    @included_with_gate.get("/gadgets")
    async def gated_at_include():  # pragma: no cover
        return {}

    parent = APIRouter()
    parent.include_router(staff, prefix="/v1")
    parent.include_router(open_router, prefix="/v1")
    parent.include_router(included_with_gate, prefix="/v1", dependencies=[Depends(get_current_staff_user)])
    app.include_router(parent, prefix="/api")

    async def plain_starlette_route(request):  # pragma: no cover
        return None

    app.add_route("/legacy", plain_starlette_route, methods=["GET"])
    app.mount("/uploads", FastAPI())  # a sub-app is never a reviewed static mount
    return app


def test_checker_flags_a_new_unlisted_route():
    problems = ungated_routes(_mini_app(), allowlist={})
    joined = "\n".join(problems)
    assert any(p.startswith("GET /api/v1/widgets/{widget_id} ->") for p in problems), joined
    assert any(p.startswith("POST /api/v1/widgets/import ->") for p in problems), joined
    assert any(p.startswith("WEBSOCKET /api/v1/widgets/live ->") for p in problems), joined
    assert any(p.startswith("GET /legacy ->") for p in problems), joined
    assert any(p.startswith("MOUNT '/uploads'") for p in problems), joined
    # Router-level, include-level and nested gates all count.
    assert not any(p.startswith("GET /api/v1/widgets ->") for p in problems), joined
    assert not any(p.startswith("GET /api/v1/gadgets ->") for p in problems), joined
    assert not any(p.startswith("DELETE /api/v1/widgets/{widget_id} ->") for p in problems), joined


def test_checker_honours_allowlist_but_only_static_mounts():
    app = _mini_app()
    allow = {
        ("GET", "/api/v1/widgets/{widget_id}"): Entry("customer", "test"),
        ("POST", "/api/v1/widgets/import"): Entry("public", "test"),
        ("WEBSOCKET", "/api/v1/widgets/live"): Entry("service", "test"),
        ("GET", "/legacy"): Entry("public", "test"),
        ("MOUNT", "/uploads"): Entry("public", "test"),
    }
    problems = ungated_routes(app, allowlist=allow)
    assert problems == ["MOUNT '/uploads' (FastAPI) is not a reviewed static mount"], problems
