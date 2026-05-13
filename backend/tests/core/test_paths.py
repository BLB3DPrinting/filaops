"""
Tests for app.core.paths — runtime-configurable filesystem path helpers.

Coverage:
- Each resolver returns its historical default when no override is supplied.
- Each resolver honours a non-blank override string by returning Path(override).
- Empty / whitespace overrides fall through to the default
  (matches the existing settings.UPLOAD_DIR convention in file_storage.py).
- resolve_upload_products_dir composes with an explicit static_dir override.

The functions are pure: no module-level side effects, no settings dependency,
no filesystem touches. Tests stay isolated and quick.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.paths import (
    _BACKEND_DIR,
    resolve_static_dir,
    resolve_upload_po_docs_dir,
    resolve_upload_products_dir,
)


# ---------------------------------------------------------------------------
# resolve_static_dir
# ---------------------------------------------------------------------------


def test_resolve_static_dir_default_when_none():
    assert resolve_static_dir(None) == _BACKEND_DIR / "static"


def test_resolve_static_dir_default_when_empty():
    assert resolve_static_dir("") == _BACKEND_DIR / "static"


def test_resolve_static_dir_default_when_whitespace():
    assert resolve_static_dir("   ") == _BACKEND_DIR / "static"


def test_resolve_static_dir_honours_override():
    assert resolve_static_dir("/tmp/custom/static") == Path("/tmp/custom/static")


def test_resolve_static_dir_strips_whitespace_around_override():
    assert resolve_static_dir("  /tmp/custom/static  ") == Path("/tmp/custom/static")


# ---------------------------------------------------------------------------
# resolve_upload_products_dir
# ---------------------------------------------------------------------------


def test_resolve_upload_products_dir_default_uses_default_static():
    assert resolve_upload_products_dir(None) == _BACKEND_DIR / "static" / "uploads" / "products"


def test_resolve_upload_products_dir_default_composes_with_explicit_static():
    custom_static = Path("/srv/filaops/static")
    assert (
        resolve_upload_products_dir(None, static_dir=custom_static)
        == custom_static / "uploads" / "products"
    )


def test_resolve_upload_products_dir_honours_override_ignoring_static_dir():
    """Override takes precedence: if the caller wants the products dir
    elsewhere entirely, the parent static_dir should be ignored."""
    overridden = resolve_upload_products_dir(
        "/var/lib/filaops/products", static_dir=Path("/srv/filaops/static")
    )
    assert overridden == Path("/var/lib/filaops/products")


def test_resolve_upload_products_dir_empty_falls_through():
    assert resolve_upload_products_dir("") == _BACKEND_DIR / "static" / "uploads" / "products"


# ---------------------------------------------------------------------------
# resolve_upload_po_docs_dir
# ---------------------------------------------------------------------------


def test_resolve_upload_po_docs_dir_default():
    assert resolve_upload_po_docs_dir(None) == _BACKEND_DIR / "uploads" / "po_documents"


def test_resolve_upload_po_docs_dir_honours_override():
    assert (
        resolve_upload_po_docs_dir("/var/lib/filaops/po_docs")
        == Path("/var/lib/filaops/po_docs")
    )


def test_resolve_upload_po_docs_dir_empty_falls_through():
    assert resolve_upload_po_docs_dir("") == _BACKEND_DIR / "uploads" / "po_documents"


# ---------------------------------------------------------------------------
# Backend directory anchor sanity check
# ---------------------------------------------------------------------------


def test_backend_dir_anchor_resolves_to_backend_root():
    """_BACKEND_DIR should resolve to the backend/ root — the directory that
    contains app/, migrations/, and pyproject.toml. Sanity-check so the
    default paths can't silently drift if someone moves app/core/paths.py."""
    # The anchor must be the parent of app/
    assert (_BACKEND_DIR / "app").is_dir(), (
        f"_BACKEND_DIR resolved to {_BACKEND_DIR!s}, but expected the backend/ root "
        "(parent dir of app/)."
    )
