"""Regression: static GET routes under /production-orders must resolve, not be
shadowed by the dynamic detail route.

The bare detail routes are constrained to ``/{order_id:int}``, so a non-integer
single segment (``/scrap-reasons``, ``/qc-statuses``, ``/operation-statuses``)
falls through to its static handler instead of being parsed as an order_id → 422.
(``/defect-reasons`` is added in #817 and covered by its own suite.) Also guards
the status-description maps against enum drift. (cortex observation #193.)
"""
PREFIX = "/api/v1/production-orders"


class TestStaticRoutesNotShadowed:
    def test_scrap_reasons_resolves(self, client):
        r = client.get(f"{PREFIX}/scrap-reasons")
        assert r.status_code == 200, r.text
        assert "details" in r.json()

    def test_qc_statuses_resolves(self, client):
        r = client.get(f"{PREFIX}/qc-statuses")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "statuses" in body and "passed" in body["statuses"]

    def test_operation_statuses_resolves(self, client):
        r = client.get(f"{PREFIX}/operation-statuses")
        assert r.status_code == 200, r.text
        assert "statuses" in r.json()

    def test_detail_route_still_works_for_int(self, client, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id)
        r = client.get(f"{PREFIX}/{po.id}")
        assert r.status_code == 200, r.text
        assert r.json()["id"] == po.id

    def test_detail_route_404_for_missing_int(self, client):
        r = client.get(f"{PREFIX}/999999")
        assert r.status_code == 404


class TestStatusDescriptionCoverage:
    """Drift guard: every status enum member must have an explicit description,
    so a new/renamed value fails HERE (at CI) rather than silently serving a
    blank description in the API."""

    def test_qc_status_descriptions_cover_all_members(self):
        # Import the SAME QCStatus the endpoint uses (status_config, not schemas)
        # so the map is checked against the enum actually iterated.
        from app.api.v1.endpoints.production_orders import QC_STATUS_DESCRIPTIONS, QCStatus
        assert set(QC_STATUS_DESCRIPTIONS) == {m.value for m in QCStatus}

    def test_operation_status_descriptions_cover_all_members(self):
        from app.api.v1.endpoints.production_orders import OPERATION_STATUS_DESCRIPTIONS, OperationStatus
        assert set(OPERATION_STATUS_DESCRIPTIONS) == {m.value for m in OperationStatus}
