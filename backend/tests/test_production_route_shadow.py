"""Regression: static GET routes under /production-orders must resolve, not be
shadowed by the dynamic detail route.

The bare detail routes are constrained to ``/{order_id:int}``, so a non-integer
single segment (``/scrap-reasons``, ``/qc-statuses``, ``/defect-reasons``) falls
through to its static handler instead of being parsed as an order_id → 422.
(cortex observation #193.)
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
