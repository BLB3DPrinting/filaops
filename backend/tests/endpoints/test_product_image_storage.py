"""Product images live on the persistent uploads volume.

Product images used to be written to <backend>/static/uploads/products, which
in Docker is /app/static/... inside the container, not on the /app/uploads
volume, so every container recreate (each upgrade) deleted them. They now go
to <backend>/uploads/products, are still served at the same
/static/uploads/products/<name> URL, and images saved under the old location
keep resolving.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from app.core.paths import BACKEND_DIR
from app.core.static_files import MultiDirStaticFiles

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


# ---------------------------------------------------------------------------
# MultiDirStaticFiles
# ---------------------------------------------------------------------------


@pytest.fixture
def two_dirs(tmp_path):
    primary = tmp_path / "primary"
    legacy = tmp_path / "legacy"
    primary.mkdir()
    legacy.mkdir()
    app = Starlette()
    app.mount("/img", MultiDirStaticFiles(directories=[primary, legacy]))
    return primary, legacy, TestClient(app)


def test_multidir_serves_from_primary_first(two_dirs):
    primary, legacy, client = two_dirs
    (primary / "a.png").write_bytes(b"new")
    (legacy / "a.png").write_bytes(b"old")
    resp = client.get("/img/a.png")
    assert resp.status_code == 200
    assert resp.content == b"new"


def test_multidir_falls_back_to_legacy(two_dirs):
    _, legacy, client = two_dirs
    (legacy / "b.png").write_bytes(b"old")
    resp = client.get("/img/b.png")
    assert resp.status_code == 200
    assert resp.content == b"old"


def test_multidir_404_when_in_neither(two_dirs):
    _, _, client = two_dirs
    assert client.get("/img/missing.png").status_code == 404


def test_multidir_blocks_path_traversal(two_dirs, tmp_path):
    _, _, client = two_dirs
    (tmp_path / "secret.txt").write_text("nope")
    assert client.get("/img/../secret.txt").status_code == 404
    assert client.get("/img/%2e%2e/secret.txt").status_code == 404


def test_multidir_tolerates_missing_fallback_dir(tmp_path):
    primary = tmp_path / "primary"
    primary.mkdir()
    (primary / "c.png").write_bytes(b"x")
    app = Starlette()
    app.mount(
        "/img", MultiDirStaticFiles(directories=[primary, tmp_path / "does-not-exist"])
    )
    client = TestClient(app)
    assert client.get("/img/c.png").status_code == 200
    assert client.get("/img/d.png").status_code == 404


# ---------------------------------------------------------------------------
# The real app: default location and serving
# ---------------------------------------------------------------------------


def test_default_product_image_dir_is_on_uploads_volume():
    """With no STATIC_DIR / UPLOAD_PRODUCTS_DIR override (the Docker default),
    images go under <backend>/uploads, i.e. /app/uploads in the container."""
    from app.main import PRODUCT_UPLOADS_DIR
    from app.api.v1.endpoints.admin import uploads

    assert PRODUCT_UPLOADS_DIR == BACKEND_DIR / "uploads" / "products"
    assert uploads.UPLOAD_DIR == PRODUCT_UPLOADS_DIR


@pytest.fixture
def placed_file():
    """Write a uniquely named file into a real served directory; clean up."""
    created: list[Path] = []

    def _place(directory: Path, content: bytes = PNG_BYTES) -> str:
        directory.mkdir(parents=True, exist_ok=True)
        name = f"test-{uuid.uuid4().hex}.png"
        path = directory / name
        path.write_bytes(content)
        created.append(path)
        return name

    yield _place
    for path in created:
        path.unlink(missing_ok=True)


def test_app_serves_product_image_from_uploads_dir(unauthed_client, placed_file):
    from app.main import PRODUCT_UPLOADS_DIR

    name = placed_file(PRODUCT_UPLOADS_DIR, b"from-volume")
    resp = unauthed_client.get(f"/static/uploads/products/{name}")
    assert resp.status_code == 200
    assert resp.content == b"from-volume"


def test_app_still_serves_images_saved_under_old_location(unauthed_client, placed_file):
    from app.main import LEGACY_PRODUCT_IMAGES_DIR

    name = placed_file(LEGACY_PRODUCT_IMAGES_DIR, b"from-legacy")
    resp = unauthed_client.get(f"/static/uploads/products/{name}")
    assert resp.status_code == 200
    assert resp.content == b"from-legacy"


# ---------------------------------------------------------------------------
# Upload / delete endpoints
# ---------------------------------------------------------------------------


@pytest.fixture
def upload_dirs(tmp_path, monkeypatch):
    from app.api.v1.endpoints.admin import uploads

    primary = tmp_path / "uploads" / "products"
    legacy = tmp_path / "static" / "uploads" / "products"
    legacy.mkdir(parents=True)
    monkeypatch.setattr(uploads, "UPLOAD_DIR", primary)
    monkeypatch.setattr(uploads, "LEGACY_DIR", legacy)
    return primary, legacy


def test_upload_writes_to_upload_dir_and_keeps_url_format(client, upload_dirs):
    primary, legacy = upload_dirs
    resp = client.post(
        "/api/v1/admin/uploads/product-image",
        files={"file": ("plate.png", PNG_BYTES, "image/png")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["url"] == f"/static/uploads/products/{body['filename']}"
    assert body["filename"].endswith(".png")
    assert (primary / body["filename"]).read_bytes() == PNG_BYTES
    assert not any(legacy.iterdir())


def test_delete_removes_image_from_upload_dir(client, upload_dirs):
    primary, _ = upload_dirs
    primary.mkdir(parents=True)
    (primary / "abc.png").write_bytes(PNG_BYTES)
    resp = client.delete("/api/v1/admin/uploads/product-image/abc.png")
    assert resp.status_code == 200
    assert not (primary / "abc.png").exists()


def test_delete_removes_image_saved_under_old_location(client, upload_dirs):
    _, legacy = upload_dirs
    (legacy / "old.png").write_bytes(PNG_BYTES)
    resp = client.delete("/api/v1/admin/uploads/product-image/old.png")
    assert resp.status_code == 200
    assert not (legacy / "old.png").exists()


def test_delete_404_when_in_neither(client, upload_dirs):
    resp = client.delete("/api/v1/admin/uploads/product-image/none.png")
    assert resp.status_code == 404
