"""PR-5 (#784): item Quality Plan CRUD."""
PLANS = "/api/v1/quality-plans"


def _plan_body(product_id, code="QP-1"):
    return {
        "product_id": product_id,
        "code": code,
        "name": "Inspection Plan",
        "characteristics": [
            {"characteristic": "bore", "nominal": "10.0", "lower_limit": "9.9",
             "upper_limit": "10.1", "unit": "mm", "severity": "major"},
            {"characteristic": "finish", "severity": "minor"},
        ],
    }


class TestQualityPlans:
    def test_create_and_get(self, client, db, make_product):
        product = make_product()
        r = client.post(PLANS, json=_plan_body(product.id))
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["product_id"] == product.id
        assert len(data["characteristics"]) == 2
        assert data["characteristics"][0]["characteristic"] == "bore"

        got = client.get(f"{PLANS}/{data['id']}")
        assert got.status_code == 200
        assert got.json()["code"] == "QP-1"

    def test_characteristic_code_round_trips(self, client, db, make_product):
        product = make_product()
        body = _plan_body(product.id, code="QP-CODE1")
        body["characteristics"] = [
            {"characteristic": "Bore diameter", "code": "BORE_DIA", "unit": "mm"},
            {"characteristic": "Surface finish", "code": "FINISH"},
        ]
        r = client.post(PLANS, json=body)
        assert r.status_code == 201, r.text
        assert [c["code"] for c in r.json()["characteristics"]] == ["BORE_DIA", "FINISH"]

    def test_rejects_duplicate_characteristic_codes(self, client, db, make_product):
        product = make_product()
        body = _plan_body(product.id, code="QP-CODE2")
        body["characteristics"] = [
            {"characteristic": "a", "code": "DUP"},
            {"characteristic": "b", "code": "DUP"},
        ]
        assert client.post(PLANS, json=body).status_code == 400

    def test_update_rejects_duplicate_characteristic_codes(self, client, db, make_product):
        product = make_product()
        create_r = client.post(PLANS, json=_plan_body(product.id, code="QP-PD1"))
        assert create_r.status_code == 201, create_r.text
        pid = create_r.json()["id"]
        r = client.patch(f"{PLANS}/{pid}", json={"characteristics": [
            {"characteristic": "a", "code": "DUP"},
            {"characteristic": "b", "code": "DUP"},
        ]})
        assert r.status_code == 400  # the update replace path validates like create
        assert "duplicate characteristic code" in r.json()["detail"]

    def test_blank_codes_normalize_to_null_and_do_not_collide(self, client, db, make_product):
        product = make_product()
        body = _plan_body(product.id, code="QP-BLANK")
        body["characteristics"] = [
            {"characteristic": "a", "code": "   "},  # whitespace -> NULL
            {"characteristic": "b", "code": ""},      # empty -> NULL
        ]
        r = client.post(PLANS, json=body)
        assert r.status_code == 201, r.text  # two blanks don't collide on the index
        assert [c["code"] for c in r.json()["characteristics"]] == [None, None]

    def test_list_by_product(self, client, db, make_product):
        product = make_product()
        client.post(PLANS, json=_plan_body(product.id, code="QP-L1"))
        r = client.get(f"{PLANS}?product_id={product.id}")
        assert r.status_code == 200
        assert "QP-L1" in [p["code"] for p in r.json()]

    def test_update_replaces_characteristics(self, client, db, make_product):
        product = make_product()
        pid = client.post(PLANS, json=_plan_body(product.id, code="QP-U1")).json()["id"]
        r = client.patch(
            f"{PLANS}/{pid}",
            json={"name": "Updated", "characteristics": [{"characteristic": "weight", "unit": "g"}]},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "Updated"
        assert [c["characteristic"] for c in data["characteristics"]] == ["weight"]

    def test_deactivate_excludes_from_default_list(self, client, db, make_product):
        product = make_product()
        pid = client.post(PLANS, json=_plan_body(product.id, code="QP-D1")).json()["id"]
        d = client.delete(f"{PLANS}/{pid}")
        assert d.status_code == 200
        assert d.json()["is_active"] is False
        active = [p["id"] for p in client.get(f"{PLANS}?product_id={product.id}").json()]
        assert pid not in active
        allp = [p["id"] for p in client.get(f"{PLANS}?product_id={product.id}&include_inactive=true").json()]
        assert pid in allp

    def test_rejects_inverted_limits(self, client, db, make_product):
        product = make_product()
        body = _plan_body(product.id, code="QP-X1")
        body["characteristics"] = [{"characteristic": "x", "lower_limit": "10", "upper_limit": "5"}]
        assert client.post(PLANS, json=body).status_code == 422

    def test_rejects_bad_severity(self, client, db, make_product):
        product = make_product()
        body = _plan_body(product.id, code="QP-X2")
        body["characteristics"] = [{"characteristic": "x", "severity": "huge"}]
        assert client.post(PLANS, json=body).status_code == 422

    def test_rejects_unknown_product(self, client, db):
        assert client.post(PLANS, json=_plan_body(999999, code="QP-X3")).status_code == 400

    def test_update_rejects_null_is_template(self, client, db, make_product):
        product = make_product()
        pid = client.post(PLANS, json=_plan_body(product.id, code="QP-N1")).json()["id"]
        r = client.patch(f"{PLANS}/{pid}", json={"is_template": None})
        assert r.status_code == 400  # not a 500 at commit

    def test_update_can_convert_product_plan_to_template(self, client, db, make_product):
        product = make_product()
        pid = client.post(PLANS, json=_plan_body(product.id, code="QP-C1")).json()["id"]
        r = client.patch(f"{PLANS}/{pid}", json={"product_id": None, "is_template": True})
        assert r.status_code == 200, r.text
        assert r.json()["is_template"] is True
        assert r.json()["product_id"] is None

    def test_update_clearing_product_without_template_is_rejected(self, client, db, make_product):
        product = make_product()
        pid = client.post(PLANS, json=_plan_body(product.id, code="QP-C2")).json()["id"]
        r = client.patch(f"{PLANS}/{pid}", json={"product_id": None})  # still not a template
        assert r.status_code == 400

    def test_template_must_not_have_product(self, client, db, make_product):
        product = make_product()
        body = _plan_body(product.id, code="QP-T1")
        body["is_template"] = True  # contradicts the product_id
        assert client.post(PLANS, json=body).status_code == 422

    def test_product_plan_requires_a_product(self, client, db):
        body = {"code": "QP-T2", "name": "x", "characteristics": []}  # not a template, no product
        assert client.post(PLANS, json=body).status_code == 422

    def test_template_without_product_is_ok(self, client, db):
        body = {
            "code": "QP-T3", "name": "Template", "is_template": True,
            "characteristics": [{"characteristic": "length", "unit": "mm"}],
        }
        r = client.post(PLANS, json=body)
        assert r.status_code == 201, r.text
        assert r.json()["is_template"] is True
        assert r.json()["product_id"] is None

    def test_create_attribute_characteristic(self, client, db, make_product):
        product = make_product()
        body = _plan_body(product.id, code="QP-ATTR")
        body["characteristics"] = [
            {
                "characteristic": "Surface defects",
                "characteristic_type": "attribute",
                "acceptance_criteria": "No visible scratches or layer shifts",
                "severity": "major",
            }
        ]
        r = client.post(PLANS, json=body)
        assert r.status_code == 201, r.text
        c = r.json()["characteristics"][0]
        assert c["characteristic_type"] == "attribute"
        assert c["acceptance_criteria"] == "No visible scratches or layer shifts"
        assert c["lower_limit"] is None and c["upper_limit"] is None

    def test_characteristic_type_defaults_to_variable(self, client, db, make_product):
        product = make_product()
        r = client.post(PLANS, json=_plan_body(product.id, code="QP-VARDEF"))
        assert r.status_code == 201, r.text
        assert all(
            c["characteristic_type"] == "variable"
            for c in r.json()["characteristics"]
        )

    def test_attribute_characteristic_rejects_spec_limits(self, client, db, make_product):
        product = make_product()
        body = _plan_body(product.id, code="QP-ATTRX")
        body["characteristics"] = [
            {
                "characteristic": "bore",
                "characteristic_type": "attribute",
                "upper_limit": "10.0",  # limits make no sense for pass/fail
            }
        ]
        assert client.post(PLANS, json=body).status_code == 422

    def test_rejects_unknown_characteristic_type(self, client, db, make_product):
        product = make_product()
        body = _plan_body(product.id, code="QP-ATTRT")
        body["characteristics"] = [
            {"characteristic": "x", "characteristic_type": "bogus"}
        ]
        assert client.post(PLANS, json=body).status_code == 422

    def test_variable_characteristic_rejects_acceptance_criteria(self, client, db, make_product):
        product = make_product()
        body = _plan_body(product.id, code="QP-VARAC")
        body["characteristics"] = [
            {
                "characteristic": "bore",
                "characteristic_type": "variable",
                "acceptance_criteria": "no scratches",  # only valid for attribute
            }
        ]
        assert client.post(PLANS, json=body).status_code == 422

    def test_attribute_characteristic_allows_blank_unit(self, client, db, make_product):
        product = make_product()
        body = _plan_body(product.id, code="QP-ATTRBU")
        body["characteristics"] = [
            {"characteristic": "finish", "characteristic_type": "attribute", "unit": "  "}
        ]
        # A blank unit is "no unit", not a spec — it must not 422.
        r = client.post(PLANS, json=body)
        assert r.status_code == 201, r.text
        assert r.json()["characteristics"][0]["unit"] is None

    def test_get_active_plan_returns_the_active_plan(self, client, db, make_product):
        product = make_product()
        client.post(PLANS, json=_plan_body(product.id, code="QP-ACT"))
        # Hitting /active (not /{plan_id}) — also asserts the route isn't shadowed.
        r = client.get(f"{PLANS}/active?product_id={product.id}")
        assert r.status_code == 200, r.text
        assert r.json()["code"] == "QP-ACT"

    def test_get_active_plan_null_when_none(self, client, db, make_product):
        product = make_product()
        r = client.get(f"{PLANS}/active?product_id={product.id}")
        assert r.status_code == 200
        assert r.json() is None

    def test_get_active_plan_excludes_inactive(self, client, db, make_product):
        product = make_product()
        pid = client.post(PLANS, json=_plan_body(product.id, code="QP-ACT2")).json()["id"]
        client.delete(f"{PLANS}/{pid}")  # deactivate
        r = client.get(f"{PLANS}/active?product_id={product.id}")
        assert r.status_code == 200
        assert r.json() is None  # only an inactive plan exists -> null
