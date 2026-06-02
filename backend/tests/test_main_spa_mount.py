"""
Regression tests for the SPA mount in app.main.

Background:
    PR #605 introduced an `_SPAStaticFiles` mount at "/" that falls back to
    `index.html` for any unmatched path. That fallback masked a routing
    quirk: FastAPI registers list endpoints as `/` under a router prefix
    (e.g. `/api/v1/purchase-orders/`), and relies on `redirect_slashes=True`
    to redirect `/api/v1/purchase-orders` (no slash) to the canonical
    trailing-slash form. Mounted apps win route resolution **before**
    redirect_slashes fires, so the SPA mount caught the no-slash request
    and returned 200 + HTML. The SPA's `apiClient` then parsed the HTML as
    text and stored it in dashboard state, where `string.length > 0` is
    true but `string.map` is undefined → `TypeError: _.map is not a
    function` on a fresh install.

These tests exercise the fix:
    * `/api/...` and `/static/...` without trailing slash → 307 to canonical
    * Canonical-but-still-unmatched API paths → 404 (not index.html)
    * Genuine client-side routes (e.g. `/admin/items`) → index.html
    * Real static assets under the SPA dir still serve normally

The fixture spins up a minimal `app.main` with `FRONTEND_DIST` pointed at a
temporary directory holding a stub `index.html` + one asset, so the tests
don't depend on the real React build.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def spa_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Reload app.main with FRONTEND_DIST pointed at a temp SPA dir.

    `app.main` resolves FRONTEND_DIST at module-import time, so we have to
    set the env var and reload the module to exercise the SPA-mount branch.
    Once we're done we restore the original module so other tests aren't
    affected.
    """
    # Stage a minimal SPA layout: index.html at root, one asset under assets/
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><html><body>spa</body></html>")
    (dist / "assets" / "shell.js").write_text("// spa asset")

    monkeypatch.setenv("FRONTEND_DIST", str(dist))

    # pydantic-settings caches the Settings instance at app.core.settings
    # import time (via @lru_cache on get_settings()), so we have to drop
    # the whole chain — app.main, app.core.config, app.core.settings — so
    # the reload picks up the env var. Stash the prior modules so other
    # tests in the same session aren't disturbed.
    #
    # The import + yield both live inside the try/finally so a failure
    # during import_module doesn't leak the popped entries — without that
    # guard a regression in app.main would cascade into every subsequent
    # test that imports the FastAPI app.
    cached_names = ("app.main", "app.core.config", "app.core.settings")
    priors = {name: sys.modules.pop(name, None) for name in cached_names}
    try:
        main = importlib.import_module("app.main")
        yield main.app, dist
    finally:
        for name in cached_names:
            sys.modules.pop(name, None)
        for name, prior in priors.items():
            if prior is not None:
                sys.modules[name] = prior


@pytest.fixture()
def multi_surface_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Reload app.main with Core, Portal Admin, Portal, and Quoter SPAs.

    The local-first PRO install serves distinct SPAs from one Core process.
    This fixture stages minimal dist folders for each surface so route tests
    prove prefixed surfaces are mounted before the root Core SPA catch-all.
    """

    def make_dist(name: str, body: str) -> Path:
        dist = tmp_path / name
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text(
            f"<!doctype html><html><body>{body}</body></html>"
        )
        (dist / "assets" / "surface.js").write_text(f"// {body} asset")
        return dist

    core_dist = make_dist("core", "core-spa")
    portal_admin_dist = make_dist("portal-admin", "portal-admin-spa")
    portal_dist = make_dist("portal", "portal-spa")
    quoter_dist = make_dist("quoter", "quoter-spa")

    monkeypatch.setenv("FRONTEND_DIST", str(core_dist))
    monkeypatch.setenv("PORTAL_ADMIN_DIST", str(portal_admin_dist))
    monkeypatch.setenv("PORTAL_DIST", str(portal_dist))
    monkeypatch.setenv("QUOTER_DIST", str(quoter_dist))

    cached_names = ("app.main", "app.core.config", "app.core.settings")
    priors = {name: sys.modules.pop(name, None) for name in cached_names}
    try:
        main = importlib.import_module("app.main")
        yield main.app
    finally:
        for name in cached_names:
            sys.modules.pop(name, None)
        for name, prior in priors.items():
            if prior is not None:
                sys.modules[name] = prior


def test_api_path_without_trailing_slash_redirects_to_canonical(spa_app):
    """The bug: `/api/v1/purchase-orders` (no slash) used to return 200 +
    index.html. After the fix it must 307 to `/api/v1/purchase-orders/`
    with the query string preserved."""
    app, _ = spa_app
    client = TestClient(app, follow_redirects=False)

    resp = client.get("/api/v1/does-not-exist-but-shape-matters?limit=5")

    assert resp.status_code == 307, (
        "API paths without a trailing slash must redirect to the canonical "
        "form so the apiClient never sees HTML in a JSON response."
    )
    location = resp.headers["location"]
    assert location.startswith("/api/v1/does-not-exist-but-shape-matters/")
    assert "limit=5" in location, "Query string must survive the redirect"


def test_static_path_without_trailing_slash_redirects_to_canonical(spa_app):
    """`static/` is reserved as defense-in-depth: the `/static` StaticFiles
    mount registers conditionally (only when its directory mkdir succeeds
    — see backend/app/main.py around the /static mount). On a read-only
    install the `/static` mount is skipped, and the SPA mount becomes the
    only thing between a `/static/*` request and an index.html fallback.

    Simulate that scenario by stripping the `/static` mount from the
    route table after fixture setup, then verify the SPA mount redirects
    the no-slash request to its canonical form instead of returning the
    SPA shell."""
    app, _ = spa_app
    app.router.routes = [
        r for r in app.router.routes if getattr(r, "path", "") != "/static"
    ]
    client = TestClient(app, follow_redirects=False)

    resp = client.get("/static/uploads/missing-asset?cache=1")

    assert resp.status_code == 307
    location = resp.headers["location"]
    assert location.startswith("/static/uploads/missing-asset/")
    assert "cache=1" in location


def test_bare_reserved_prefix_returns_404_not_index_html(spa_app):
    """A request to `/api` (bare, no path segment after it) used to fall
    through to the SPA shell because `_RESERVED_PREFIXES` only matched
    `api/`. After the fix the reserved check operates on the first URL
    segment, so bare `/api` is recognised and returns a JSON 404."""
    app, _ = spa_app
    client = TestClient(app, follow_redirects=False)

    resp = client.get("/api")
    assert resp.status_code == 404
    assert "text/html" not in resp.headers.get("content-type", "")


def test_unreserved_segment_resembling_reserved_still_falls_back(spa_app):
    """Routing must compare against the first URL segment as a whole, not
    a prefix substring. `/apidocs` and `/staticky/items` share opening
    characters with reserved prefixes but are legitimate client-side
    routes — they must still resolve to the SPA shell."""
    app, _ = spa_app
    client = TestClient(app)

    for path in ("/apidocs", "/staticky/items"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "spa" in resp.text, path


def test_canonical_api_path_404_does_not_fall_back_to_index_html(spa_app):
    """Once the path is in canonical form (trailing slash) and still
    doesn't match any route, the SPA mount must let the 404 stand. Falling
    back to index.html here would re-introduce the original bug for any
    URL that actually IS misspelled or removed."""
    app, _ = spa_app
    client = TestClient(app, follow_redirects=False)

    resp = client.get("/api/v1/genuinely-missing/")
    assert resp.status_code == 404
    assert "text/html" not in resp.headers.get("content-type", "")


def test_client_side_route_falls_back_to_index_html(spa_app):
    """The original SPA-fallback behavior is preserved for non-API paths:
    a request to a client-side route like `/admin/items` returns the SPA
    shell so the React router can take over."""
    app, dist = spa_app
    client = TestClient(app)

    resp = client.get("/admin/items")
    assert resp.status_code == 200
    assert "spa" in resp.text  # the stub index.html body
    assert "text/html" in resp.headers["content-type"]


def test_real_spa_asset_serves_from_disk(spa_app):
    """Real files under the SPA dist (hashed Vite assets, favicon, etc.)
    must still serve their actual bytes, not the index.html fallback."""
    app, _ = spa_app
    client = TestClient(app)

    resp = client.get("/assets/shell.js")
    assert resp.status_code == 200
    assert "spa asset" in resp.text


def test_root_serves_index_html_when_spa_mounted(spa_app):
    """When FRONTEND_DIST is set, `GET /` returns the SPA shell rather
    than the API status JSON — confirms the root handler branch."""
    app, _ = spa_app
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    assert "<!doctype html>" in resp.text.lower()


def test_portal_admin_surface_serves_own_spa(multi_surface_app):
    client = TestClient(multi_surface_app)

    resp = client.get("/portal-admin/admin/quote-config")

    assert resp.status_code == 200
    assert "portal-admin-spa" in resp.text
    assert "core-spa" not in resp.text


def test_surface_roots_serve_own_spas_without_trailing_slash(multi_surface_app):
    client = TestClient(multi_surface_app)

    expected = {
        "/portal-admin": "portal-admin-spa",
        "/portal": "portal-spa",
        "/quote": "quoter-spa",
    }
    for path, body in expected.items():
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert body in resp.text, path
        assert "core-spa" not in resp.text, path


def test_b2b_portal_surface_serves_own_spa(multi_surface_app):
    client = TestClient(multi_surface_app)

    resp = client.get("/portal/catalog")

    assert resp.status_code == 200
    assert "portal-spa" in resp.text
    assert "core-spa" not in resp.text


def test_quoter_surface_serves_own_spa(multi_surface_app):
    client = TestClient(multi_surface_app)

    resp = client.get("/quote/result/Q-123")

    assert resp.status_code == 200
    assert "quoter-spa" in resp.text
    assert "core-spa" not in resp.text


def test_surface_assets_serve_from_surface_dist(multi_surface_app):
    client = TestClient(multi_surface_app)

    resp = client.get("/quote/assets/surface.js")

    assert resp.status_code == 200
    assert "quoter-spa asset" in resp.text
