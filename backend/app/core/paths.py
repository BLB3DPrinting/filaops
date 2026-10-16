"""
Path resolution helpers for runtime-configurable filesystem locations.

The functions here let modules that need to write to the filesystem
(uploads, static files, audit logs, etc.) honour env-var-driven overrides
while still falling back to sensible per-checkout defaults.

Why this exists:
    Several module-level constants in the app historically used
    ``Path(__file__).parent.parent...`` to find a writable directory
    relative to the source tree. That works in Docker and in local dev
    (the source tree is writable) but breaks under any deployment that
    puts the application bundle in a read-only location — notably
    PyInstaller-frozen installs sitting under ``C:\\Program Files\\``.

    These helpers preserve the existing default behaviour when no
    override is supplied, so Docker / dev installs are unaffected.
    A packaged install can set e.g. ``STATIC_DIR`` to a writable
    per-user location.

Environment variable note:
    Settings reads env vars *unprefixed* (its model_config does not set
    ``env_prefix``). The active env var names match the field names on
    ``Settings`` exactly — ``STATIC_DIR``, ``UPLOAD_PRODUCTS_DIR``,
    ``UPLOAD_PO_DOCS_DIR``. The ``Settings`` class docstring mentions a
    ``FILAOPS_`` prefix but no such prefix is currently configured; that
    pre-existing claim is misleading and worth fixing in a follow-up.

Pattern:
    The caller passes the raw override string (typically from
    ``settings.FOO``) plus an explicit default. We treat empty / blank
    strings as "use the default" — matches the existing convention in
    ``app.services.file_storage`` for ``UPLOAD_DIR``.
"""
from __future__ import annotations

from pathlib import Path


# Resolves to the ``backend/`` directory at the top of the repo.
# Used as the anchor for the historical-default paths so behaviour stays
# identical when no env var is supplied.
#
# Exported (no leading underscore) because callers — notably the test
# suite, and anything else needing to anchor in the same place — may
# legitimately want to read it. Treating it as part of the module's
# public surface keeps tests from coupling to a "private" name.
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _coerce_override(value: str | None) -> Path | None:
    """Return ``Path(value)`` if ``value`` is a non-blank string, else ``None``.

    Tolerates both ``None`` and ``""`` / whitespace because pydantic-settings
    defaults string fields to ``""`` rather than ``None`` when no env var is
    present (see existing ``settings.UPLOAD_DIR`` convention).
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return Path(stripped)


def resolve_static_dir(override: str | None = None) -> Path:
    """Static files root.

    Default: ``<backend>/static`` (the historical location).
    Override: ``STATIC_DIR`` env / ``settings.STATIC_DIR``.

    Used by ``app.main`` to mount ``/static`` and as the parent for
    product image uploads.
    """
    overridden = _coerce_override(override)
    if overridden is not None:
        return overridden
    return BACKEND_DIR / "static"


def resolve_upload_products_dir(
    override: str | None = None, *, static_override: str | None = None
) -> Path:
    """Product image upload directory.

    Resolution order:
    1. ``UPLOAD_PRODUCTS_DIR`` (``override``) when set.
    2. ``<STATIC_DIR>/uploads/products`` when ``STATIC_DIR``
       (``static_override``) is set — packaged installs that moved the
       static root to a writable per-user location keep images there.
    3. Default: ``<backend>/uploads/products``. In Docker that is
       ``/app/uploads/products``, on the persistent uploads volume. The old
       default, ``<backend>/static/uploads/products``, lives inside the
       container and was wiped whenever the container was recreated.

    Images are served at ``/static/uploads/products/<name>`` from this
    directory, falling back to ``resolve_legacy_product_images_dir`` so
    images saved under the old default keep resolving (see ``app.main``).
    """
    overridden = _coerce_override(override)
    if overridden is not None:
        return overridden
    static_overridden = _coerce_override(static_override)
    if static_overridden is not None:
        return static_overridden / "uploads" / "products"
    return BACKEND_DIR / "uploads" / "products"


def resolve_legacy_product_images_dir(static_dir: Path) -> Path:
    """Where product images were written before they moved to the uploads
    volume: ``<static_dir>/uploads/products``. Still served as a fallback so
    existing ``image_url`` values keep working on installs where those files
    survived (source and packaged installs; not recreated Docker containers).
    """
    return static_dir / "uploads" / "products"


def resolve_upload_po_docs_dir(override: str | None = None) -> Path:
    """Purchase order documents upload directory.

    Default: ``<backend>/uploads/po_documents`` (kept outside the
    static-files root because PO docs are downloaded via an authenticated
    endpoint, not served via the public ``/static`` mount).
    Override: ``UPLOAD_PO_DOCS_DIR`` env / ``settings.UPLOAD_PO_DOCS_DIR``.
    """
    overridden = _coerce_override(override)
    if overridden is not None:
        return overridden
    return BACKEND_DIR / "uploads" / "po_documents"


def resolve_upload_qc_photos_dir(override: str | None = None) -> Path:
    """QC inspection photos upload directory.

    Default: ``<backend>/uploads/qc_photos`` (kept outside the static-files
    root because QC photos are downloaded via an authenticated endpoint, not
    served via the public ``/static`` mount — same rationale as PO documents).
    A dedicated directory, NOT a reuse of ``po_documents``, so the two file
    sets never collide.
    Override: ``UPLOAD_QC_PHOTOS_DIR`` env / ``settings.UPLOAD_QC_PHOTOS_DIR``.
    """
    overridden = _coerce_override(override)
    if overridden is not None:
        return overridden
    return BACKEND_DIR / "uploads" / "qc_photos"


def resolve_frontend_dist(override: str | None = None) -> Path | None:
    """React SPA dist directory, OR None if unset.

    Default: ``None`` — Core does not serve the SPA in this case. In the
    standard Docker deployment a separate web server (Caddy / nginx) sits
    in front of the API and serves the static frontend; FastAPI never
    needs to know where it lives.

    Override: ``FRONTEND_DIST`` env / ``settings.FRONTEND_DIST``. Setting
    this enables FastAPI-side SPA serving (mounted at ``/`` with a
    client-side-routing catch-all). Used by single-process deployments
    that have no separate web server — notably the PyInstaller-bundled
    desktop install where the React build sits inside the same bundle
    as the backend.

    Returns ``None`` (not a default path) when unset: callers should
    check ``is None`` and skip mounting routes rather than mounting an
    empty directory.
    """
    return _coerce_override(override)


def resolve_surface_dist(override: str | None = None) -> Path | None:
    """Customer-facing or PRO admin SPA dist directory, OR None if unset.

    This mirrors ``resolve_frontend_dist`` but keeps the call sites readable
    when Core is asked to serve additional local-first surfaces such as
    Portal Admin, the B2B Portal, or the public Quoter.
    """
    return _coerce_override(override)
