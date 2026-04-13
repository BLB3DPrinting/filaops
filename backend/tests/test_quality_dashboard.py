"""
Tests for Quality Management dashboard endpoints.

Covers:
- Inspection queue (pending/in_progress QC orders)
- Quality metrics (first-pass yield, scrap rate)
- Recent inspections listing
- Scrap summary by reason
- Authentication enforcement
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal


# =============================================================================
# Inspection Queue
# =============================================================================


class TestInspectionQueue:
    """GET /api/v1/quality/inspection-queue"""

    def test_empty_queue(self, client):
        resp = client.get("/api/v1/quality/inspection-queue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_returns_pending_orders(self, client, db, make_product, make_production_order):
        product = make_product(name="Widget A")
        po1 = make_production_order(
            product_id=product.id, status="completed",
            qc_status="pending", priority=1,
        )
        po2 = make_production_order(
            product_id=product.id, status="completed",
            qc_status="in_progress", priority=2,
        )
        # This one should NOT appear — already passed
        make_production_order(
            product_id=product.id, status="closed",
            qc_status="passed",
        )
        db.flush()

        resp = client.get("/api/v1/quality/inspection-queue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        codes = [item["code"] for item in data["items"]]
        assert po1.code in codes
        assert po2.code in codes

    def test_sorted_by_priority(self, client, db, make_product, make_production_order):
        product = make_product()
        low_prio = make_production_order(
            product_id=product.id, status="completed",
            qc_status="pending", priority=5,
        )
        high_prio = make_production_order(
            product_id=product.id, status="completed",
            qc_status="pending", priority=1,
        )
        db.flush()

        resp = client.get("/api/v1/quality/inspection-queue")
        data = resp.json()
        assert data["items"][0]["code"] == high_prio.code
        assert data["items"][1]["code"] == low_prio.code

    def test_pagination(self, client, db, make_product, make_production_order):
        product = make_product()
        for i in range(5):
            make_production_order(
                product_id=product.id, status="completed",
                qc_status="pending", priority=3,
            )
        db.flush()

        resp = client.get("/api/v1/quality/inspection-queue?limit=2&offset=0")
        assert resp.json()["total"] == 5
        assert len(resp.json()["items"]) == 2

        resp2 = client.get("/api/v1/quality/inspection-queue?limit=2&offset=2")
        assert len(resp2.json()["items"]) == 2

    def test_requires_auth(self, unauthed_client):
        resp = unauthed_client.get("/api/v1/quality/inspection-queue")
        assert resp.status_code == 401


# =============================================================================
# Quality Metrics
# =============================================================================


class TestQualityMetrics:
    """GET /api/v1/quality/metrics"""

    def test_empty_metrics(self, client):
        resp = client.get("/api/v1/quality/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_inspections"] == 0
        assert data["first_pass_yield"] is None
        assert data["scrap_rate"] is None

    def test_first_pass_yield_calculation(self, client, db, make_product, make_production_order):
        product = make_product()
        now = datetime.now(timezone.utc)

        # 3 passed, 1 failed → yield = 75%
        for _ in range(3):
            make_production_order(
                product_id=product.id, status="closed",
                qc_status="passed", qc_inspected_at=now,
                quantity=Decimal("10"),
            )
        make_production_order(
            product_id=product.id, status="qc_hold",
            qc_status="failed", qc_inspected_at=now,
            quantity=Decimal("10"),
        )
        db.flush()

        resp = client.get("/api/v1/quality/metrics?days=30")
        data = resp.json()
        assert data["passed"] == 3
        assert data["failed"] == 1
        assert data["total_inspections"] == 4
        assert data["first_pass_yield"] == 75.0

    def test_pending_count(self, client, db, make_product, make_production_order):
        product = make_product()
        make_production_order(
            product_id=product.id, status="completed",
            qc_status="pending",
        )
        make_production_order(
            product_id=product.id, status="completed",
            qc_status="in_progress",
        )
        db.flush()

        resp = client.get("/api/v1/quality/metrics")
        assert resp.json()["pending_inspections"] == 2

    def test_days_parameter(self, client):
        resp = client.get("/api/v1/quality/metrics?days=7")
        assert resp.status_code == 200
        assert resp.json()["period_days"] == 7

    def test_requires_auth(self, unauthed_client):
        resp = unauthed_client.get("/api/v1/quality/metrics")
        assert resp.status_code == 401


# =============================================================================
# Recent Inspections
# =============================================================================


class TestRecentInspections:
    """GET /api/v1/quality/recent-inspections"""

    def test_empty_list(self, client):
        resp = client.get("/api/v1/quality/recent-inspections")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_completed_inspections(self, client, db, make_product, make_production_order):
        product = make_product(name="Inspected Item")
        now = datetime.now(timezone.utc)

        make_production_order(
            product_id=product.id, status="closed",
            qc_status="passed", qc_inspected_at=now,
            qc_inspected_by="Inspector A", qc_notes="Looks good",
        )
        make_production_order(
            product_id=product.id, status="qc_hold",
            qc_status="failed", qc_inspected_at=now - timedelta(hours=1),
            qc_inspected_by="Inspector B", qc_notes="Defective",
        )
        # Pending — should NOT appear
        make_production_order(
            product_id=product.id, status="completed",
            qc_status="pending",
        )
        db.flush()

        resp = client.get("/api/v1/quality/recent-inspections")
        data = resp.json()
        assert len(data) == 2
        assert data[0]["qc_inspected_by"] == "Inspector A"  # Most recent first
        assert data[1]["qc_inspected_by"] == "Inspector B"

    def test_limit_parameter(self, client, db, make_product, make_production_order):
        product = make_product()
        now = datetime.now(timezone.utc)
        for i in range(5):
            make_production_order(
                product_id=product.id, status="closed",
                qc_status="passed",
                qc_inspected_at=now - timedelta(hours=i),
            )
        db.flush()

        resp = client.get("/api/v1/quality/recent-inspections?limit=2")
        assert len(resp.json()) == 2

    def test_requires_auth(self, unauthed_client):
        resp = unauthed_client.get("/api/v1/quality/recent-inspections")
        assert resp.status_code == 401


# =============================================================================
# Scrap Summary
# =============================================================================


class TestScrapSummary:
    """GET /api/v1/quality/scrap-summary"""

    def test_empty_summary(self, client, db):
        from app.models.production_order import ScrapRecord
        db.query(ScrapRecord).delete()
        db.flush()
        resp = client.get("/api/v1/quality/scrap-summary")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_groups_by_reason(self, client, db, make_product, make_production_order):
        from app.models.scrap_reason import ScrapReason
        from app.models.production_order import ScrapRecord

        db.query(ScrapRecord).delete()
        db.flush()

        product = make_product()
        po = make_production_order(product_id=product.id, status="qc_hold")

        reason1 = ScrapReason(code="PRINT_FAIL", name="Print Failure", active=True)
        reason2 = ScrapReason(code="MAT_DEFECT", name="Material Defect", active=True)
        db.add_all([reason1, reason2])
        db.flush()

        db.add(ScrapRecord(
            production_order_id=po.id,
            product_id=product.id,
            quantity=Decimal("5"),
            unit_cost=Decimal("2.00"),
            total_cost=Decimal("10.00"),
            scrap_reason_id=reason1.id,
            scrap_reason_code="PRINT_FAIL",
        ))
        db.add(ScrapRecord(
            production_order_id=po.id,
            product_id=product.id,
            quantity=Decimal("3"),
            unit_cost=Decimal("2.00"),
            total_cost=Decimal("6.00"),
            scrap_reason_id=reason1.id,
            scrap_reason_code="PRINT_FAIL",
        ))
        db.add(ScrapRecord(
            production_order_id=po.id,
            product_id=product.id,
            quantity=Decimal("2"),
            unit_cost=Decimal("3.00"),
            total_cost=Decimal("6.00"),
            scrap_reason_id=reason2.id,
            scrap_reason_code="MAT_DEFECT",
        ))
        db.flush()

        resp = client.get("/api/v1/quality/scrap-summary?days=30")
        data = resp.json()
        assert len(data) == 2

        # Sorted by total_cost descending → PRINT_FAIL ($16) first
        assert data[0]["reason_code"] == "PRINT_FAIL"
        assert data[0]["count"] == 2
        assert data[0]["total_quantity"] == 8.0
        assert data[0]["total_cost"] == 16.0

        assert data[1]["reason_code"] == "MAT_DEFECT"
        assert data[1]["count"] == 1

    def test_requires_auth(self, unauthed_client):
        resp = unauthed_client.get("/api/v1/quality/scrap-summary")
        assert resp.status_code == 401
