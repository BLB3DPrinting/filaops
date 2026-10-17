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


NAME = "0123456789abcdef0123456789abcdef.png"  # the shape uploads generate


def test_delete_removes_image_from_upload_dir(client, upload_dirs):
    primary, legacy = upload_dirs
    primary.mkdir(parents=True)
    (primary / NAME).write_bytes(PNG_BYTES)
    (legacy / NAME).write_bytes(PNG_BYTES)
    resp = client.delete(f"/api/v1/admin/uploads/product-image/{NAME}")
    assert resp.status_code == 200
    assert not (primary / NAME).exists()
    assert (legacy / NAME).exists()  # only the first match is deleted


def test_delete_removes_image_saved_under_old_location(client, upload_dirs):
    _, legacy = upload_dirs
    (legacy / NAME).write_bytes(PNG_BYTES)
    resp = client.delete(f"/api/v1/admin/uploads/product-image/{NAME}")
    assert resp.status_code == 200
    assert not (legacy / NAME).exists()


def test_delete_404_when_in_neither(client, upload_dirs):
    resp = client.delete(f"/api/v1/admin/uploads/product-image/{NAME}")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "raw",
    [
        "%2E%2E",  # ..
        "%2E",  # .
        "..%5C" + NAME,  # ..\<name>
        "sub%5C" + NAME,  # backslash
        "0123456789ABCDEF0123456789ABCDEF.png",  # not what uploads generate
        "not-a-uuid.png",
        "0123456789abcdef0123456789abcdef",  # no extension
        "0123456789abcdef0123456789abcdef.svg",  # extension never allowed
        "0123456789abcdef0123456789abcdef.PNG",  # uploads lowercase the extension
        "0123456789abcdef0123456789abcdef.png.txt",
        "0123456789abcdef0123456789abcdef.png%0A",  # trailing newline
    ],
)
def test_delete_rejects_names_uploads_never_generate(client, upload_dirs, raw):
    resp = client.delete(f"/api/v1/admin/uploads/product-image/{raw}")
    assert resp.status_code == 400, (raw, resp.status_code, resp.text)


def test_delete_with_slash_never_reaches_a_file(client, upload_dirs, tmp_path):
    """A '/' can't be part of the path parameter: the route doesn't match."""
    victim = tmp_path / "uploads" / NAME
    victim.parent.mkdir(parents=True, exist_ok=True)
    victim.write_bytes(PNG_BYTES)
    resp = client.delete(f"/api/v1/admin/uploads/product-image/products%2F..%2F{NAME}")
    assert resp.status_code in (400, 404, 405)
    assert victim.exists()


def test_find_stored_image_stays_inside_its_directory(upload_dirs, tmp_path):
    """Defence in depth below the name check: a name that resolves outside
    the base directory is never returned."""
    from app.api.v1.endpoints.admin import uploads

    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG_BYTES)
    assert uploads._find_stored_image("../../outside.png") is None
    assert outside.exists()
