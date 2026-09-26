"""Behaviour sweep for the route gates (companion to test_route_authz_allowlist.py).

The structural test proves every route depends on a staff or admin gate unless
it is allowlisted. This sweep calls each of those routes the way an attacker
would and checks the answer:

- customer leg: a self-registered customer's token gets 403 on every route
  that has no ALLOWLIST entry;
- anonymous leg: no credentials gets 401 on every route that has no ALLOWLIST
  entry, and on the 'customer' entries (they still need a login).

'public' and 'service' entries are never called (the /api/v1/test/* routes
seed and wipe data; test_test_endpoints_guard.py covers their guards). Path
parameters are filled with 1 and no body is sent: FastAPI solves the auth
dependencies before it validates the body or query, so 401/403 comes first.
"""
from __future__ import annotations

import re

from tests.endpoints.test_route_authz_allowlist import (
    ALLOWLIST,
    MIN_API_ROUTES,
    RouteInfo,
    collect_routes,
    is_core_route,
)

TEST_ROUTER_PREFIX = "/api/v1/test/"
GATE_DETAILS = {"Staff access required", "Admin access required"}
_PATH_PARAM = re.compile(r"\{([^}:]+)(?::[^}]+)?\}")


def _url(path: str) -> str:
    """'/items/{item_id}' -> '/items/1'; also strips convertors such as '{order_id:int}'."""
    return _PATH_PARAM.sub("1", path)


def _served_routes() -> list[RouteInfo]:
    from app.main import app

    routes = [
        r for r in collect_routes(app)
        if is_core_route(r) and r.kind in ("api", "route") and not r.path.startswith(TEST_ROUTER_PREFIX)
    ]
    api = [r for r in routes if r.kind == "api" and r.path.startswith("/api/v1/")]
    assert len(api) >= MIN_API_ROUTES, f"only {len(api)} /api/v1 routes enumerated; the sweep would prove nothing"
    return routes


def _category(route: RouteInfo) -> str | None:
    entry = ALLOWLIST.get((route.method, route.path))
    return entry.category if entry else None


def _call(client, db, route: RouteInfo, headers=None):
    response = client.request(route.method, _url(route.path), headers=headers or {})
    # Nothing a handler did may leak into the next call: before the gates land
    # a handler can run (and fail) for these callers, and a failed statement
    # would otherwise poison the shared test session for every later route.
    db.rollback()
    client.cookies.clear()
    return response


def _detail(response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:120]
    return str(body.get("detail", body))[:120] if isinstance(body, dict) else str(body)[:120]


def _report(title: str, failures: list[str], total: int) -> str:
    return f"{len(failures)} of {total} routes {title}:\n  " + "\n  ".join(failures)


def test_customer_token_gets_403_on_every_gated_route(unauthed_client, role_headers, db):
    headers = role_headers("customer")
    db.commit()  # keep the customer across the per-call rollbacks (the fixture still rolls it back)
    targets = [r for r in _served_routes() if _category(r) is None]

    failures = []
    for route in targets:
        response = _call(unauthed_client, db, route, headers)
        if response.status_code != 403:
            failures.append(f"{route.method} {route.path} -> {response.status_code} {_detail(response)!r}"
                            f" ({route.endpoint})")

    assert not failures, _report(
        "answered a customer token with something other than 403 "
        "(gate them with get_current_staff_user / get_current_admin_user)", failures, len(targets))


def test_anonymous_gets_401_on_every_non_public_route(unauthed_client, db):
    targets = [r for r in _served_routes() if _category(r) in (None, "customer")]

    failures = []
    for route in targets:
        response = _call(unauthed_client, db, route)
        if response.status_code != 401:
            failures.append(f"{route.method} {route.path} -> {response.status_code} {_detail(response)!r}"
                            f" ({route.endpoint})")

    assert not failures, _report("answered an anonymous caller with something other than 401", failures,
                                 len(targets))


def test_customer_routes_are_not_refused_by_a_staff_gate(unauthed_client, role_headers, db):
    """The Quoter and PRO call these with customer tokens (ids that do not exist: 404 is fine)."""
    headers = role_headers("customer")
    db.commit()
    targets = [r for r in _served_routes() if _category(r) == "customer"]
    assert targets, "no customer ALLOWLIST routes are served"

    refused = []
    for route in targets:
        response = _call(unauthed_client, db, route, headers)
        if response.status_code == 401 or (response.status_code == 403 and _detail(response) in GATE_DETAILS):
            refused.append(f"{route.method} {route.path} -> {response.status_code} {_detail(response)!r}")

    assert not refused, "customer routes refused a customer token:\n  " + "\n  ".join(refused)


def test_public_get_routes_do_not_ask_for_a_login(unauthed_client, db):
    """Anonymous GETs on public entries (logo, version, health, reset status) must not hit a login or role gate."""
    targets = [r for r in _served_routes() if _category(r) == "public" and r.method == "GET"]
    assert targets, "no public GET routes are served"

    refused = []
    for route in targets:
        response = _call(unauthed_client, db, route)
        if response.status_code == 401 or (response.status_code == 403 and _detail(response) in GATE_DETAILS):
            refused.append(f"{route.method} {route.path} -> {response.status_code} {_detail(response)!r}")

    assert not refused, "public routes refused an anonymous caller:\n  " + "\n  ".join(refused)
