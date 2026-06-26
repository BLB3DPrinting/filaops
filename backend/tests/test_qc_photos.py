"""PR-2 (#784 QMS): QC inspection photo upload/list/download/delete.

Photos attach to a qc_inspections row, store in a dedicated dir (here redirected
to a tmp_path so tests don't litter the repo), and respect the QC dial — when
quality_mode is 'off' the whole surface 403s.
"""
from datetime import datetime, timezone

import pytest

from app.models.production_order import QCInspection
from app.models.system_setting import SystemSetting

BASE = "/api/v1/production-orders/qc-inspections"
IMG = b"\x89PNG\r\n\x1a\n" + b"qc-evidence" * 8


@pytest.fixture
def photo_dir(tmp_path, monkeypatch):
    """Redirect the module's upload dir at request time to an isolated tmp dir."""
    monkeypatch.setattr("app.api.v1.endpoints.qc_photos.UPLOAD_DIR", tmp_path)
    return tmp_path


def _make_inspection(db, make_product, make_production_order):
    product = make_product()
    po = make_production_order(product_id=product.id, status="complete")
    insp = QCInspection(
        production_order_id=po.id,
        result="failed",
        inspected_at=datetime.now(timezone.utc),
    )
    db.add(insp)
    db.flush()
    return insp


class TestQCPhotos:
    def test_upload_list_download_roundtrip(
        self, client, db, photo_dir, make_product, make_production_order
    ):
        insp = _make_inspection(db, make_product, make_production_order)
        r = client.post(
            f"{BASE}/{insp.id}/photos",
            files={"file": ("rim.png", IMG, "image/png")},
            data={"caption": "scratch on rim"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["qc_inspection_id"] == insp.id
        assert body["caption"] == "scratch on rim"
        assert body["file_size"] == len(IMG)
        assert body["download_url"].endswith(f"/photos/{body['id']}/download")
        photo_id = body["id"]
        # file actually written to the isolated dir
        assert len(list(photo_dir.iterdir())) == 1

        lst = client.get(f"{BASE}/{insp.id}/photos").json()
        assert [p["id"] for p in lst] == [photo_id]

        dl = client.get(f"{BASE}/{insp.id}/photos/{photo_id}/download")
        assert dl.status_code == 200
        assert dl.content == IMG  # exact bytes round-trip

    def test_upload_to_missing_inspection_404(self, client, photo_dir):
        r = client.post(
            f"{BASE}/999999/photos",
            files={"file": ("x.png", IMG, "image/png")},
        )
        assert r.status_code == 404

    def test_rejects_non_image_extension(
        self, client, db, photo_dir, make_product, make_production_order
    ):
        insp = _make_inspection(db, make_product, make_production_order)
        r = client.post(
            f"{BASE}/{insp.id}/photos",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert r.status_code == 400

    def test_rejects_oversize(
        self, client, db, photo_dir, monkeypatch, make_product, make_production_order
    ):
        insp = _make_inspection(db, make_product, make_production_order)
        monkeypatch.setattr("app.api.v1.endpoints.qc_photos.MAX_PHOTO_BYTES", 8)
        r = client.post(
            f"{BASE}/{insp.id}/photos",
            files={"file": ("big.png", b"123456789", "image/png")},
        )
        assert r.status_code == 413

    def test_rejects_overlong_caption(
        self, client, db, photo_dir, make_product, make_production_order
    ):
        insp = _make_inspection(db, make_product, make_production_order)
        r = client.post(
            f"{BASE}/{insp.id}/photos",
            files={"file": ("a.png", IMG, "image/png")},
            data={"caption": "x" * 256},  # column is String(255)
        )
        assert r.status_code == 400

    def test_patch_caption(
        self, client, db, photo_dir, make_product, make_production_order
    ):
        insp = _make_inspection(db, make_product, make_production_order)
        pid = client.post(
            f"{BASE}/{insp.id}/photos",
            files={"file": ("a.png", IMG, "image/png")},
        ).json()["id"]
        r = client.patch(f"{BASE}/{insp.id}/photos/{pid}", json={"caption": "updated"})
        assert r.status_code == 200
        assert r.json()["caption"] == "updated"

    def test_delete_removes_row_and_file(
        self, client, db, photo_dir, make_product, make_production_order
    ):
        insp = _make_inspection(db, make_product, make_production_order)
        pid = client.post(
            f"{BASE}/{insp.id}/photos",
            files={"file": ("a.png", IMG, "image/png")},
        ).json()["id"]
        assert len(list(photo_dir.iterdir())) == 1

        d = client.delete(f"{BASE}/{insp.id}/photos/{pid}")
        assert d.status_code == 200
        assert client.get(f"{BASE}/{insp.id}/photos").json() == []
        assert list(photo_dir.iterdir()) == []  # local file cleaned up

    def test_off_mode_blocks_photos(
        self, client, db, photo_dir, make_product, make_production_order
    ):
        insp = _make_inspection(db, make_product, make_production_order)
        db.merge(SystemSetting(key="quality_mode", value="off"))
        db.flush()
        up = client.post(
            f"{BASE}/{insp.id}/photos",
            files={"file": ("a.png", IMG, "image/png")},
        )
        assert up.status_code == 403
        assert client.get(f"{BASE}/{insp.id}/photos").status_code == 403

    def test_requires_auth(self, unauthed_client, photo_dir):
        assert unauthed_client.get(f"{BASE}/1/photos").status_code == 401
