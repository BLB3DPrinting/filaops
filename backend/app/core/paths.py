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
    A packaged install can set e.g. ``FILAOPS_STATIC_DIR`` to a
    writable per-user location.

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
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


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
    Override: ``FILAOPS_STATIC_DIR`` env / ``settings.STATIC_DIR``.

    Used by ``app.main`` to mount ``/static`` and as the parent for
    product image uploads.
    """
    overridden = _coerce_override(override)
    if overridden is not None:
        return overridden
    return _BACKEND_DIR / "static"


def resolve_upload_products_dir(
    override: str | None = None, *, static_dir: Path | None = None
) -> Path:
    """Product image upload directory.

    Default: ``<static_dir>/uploads/products`` (kept directly under the
    static-files root so the images are web-served via the existing
    ``/static`` mount).
    Override: ``FILAOPS_UPLOAD_PRODUCTS_DIR`` env / ``settings.UPLOAD_PRODUCTS_DIR``.
    """
    overridden = _coerce_override(override)
    if overridden is not None:
        return overridden
    base = static_dir if static_dir is not None else resolve_static_dir(None)
    return base / "uploads" / "products"


def resolve_upload_po_docs_dir(override: str | None = None) -> Path:
    """Purchase order documents upload directory.

    Default: ``<backend>/uploads/po_documents`` (kept outside the
    static-files root because PO docs are downloaded via an authenticated
    endpoint, not served via the public ``/static`` mount).
    Override: ``FILAOPS_UPLOAD_PO_DOCS_DIR`` env / ``settings.UPLOAD_PO_DOCS_DIR``.
    """
    overridden = _coerce_override(override)
    if overridden is not None:
        return overridden
    return _BACKEND_DIR / "uploads" / "po_documents"
