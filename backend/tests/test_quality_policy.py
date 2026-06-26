"""PR-1 (#784 QMS dial): the quality policy read-model + GET /quality/policy.

The quality module is selectable. Default mode is 'basic' so existing installs
behave exactly as before; 'off' hides all QC surfaces; 'full' turns on
plan-driven QC with optional close-gating.
"""
import pytest

from app.models.system_setting import SystemSetting
from app.services.quality_policy import QualityMode, get_quality_policy
from app.api.v1.endpoints.system_settings import (
    _validate_bool,
    _validate_quality_mode,
)

POLICY = "/api/v1/quality/policy"


def _set(db, key, value):
    """Upsert a system_settings row (key is the PK) and make it visible."""
    db.merge(SystemSetting(key=key, value=value))
    db.flush()


class TestQualityPolicyReadModel:
    def test_default_is_basic(self, db):
        p = get_quality_policy(db)
        assert p.mode is QualityMode.BASIC
        assert p.surfaces_enabled is True   # basic still shows QC
        assert p.plan_driven is False
        assert p.gates_close is False

    def test_off_hides_surfaces(self, db):
        _set(db, "quality_mode", "off")
        p = get_quality_policy(db)
        assert p.is_off is True
        assert p.surfaces_enabled is False
        assert p.plan_driven is False

    def test_full_is_plan_driven(self, db):
        _set(db, "quality_mode", "full")
        p = get_quality_policy(db)
        assert p.is_full is True
        assert p.surfaces_enabled is True
        assert p.plan_driven is True

    def test_gates_close_requires_full_and_flag(self, db):
        # basic never gates, even with the flag on
        _set(db, "quality_mode", "basic")
        _set(db, "quality_gate_close", True)
        assert get_quality_policy(db).gates_close is False
        # full + flag => gates
        _set(db, "quality_mode", "full")
        assert get_quality_policy(db).gates_close is True
        # full without the flag => holds, does not gate
        _set(db, "quality_gate_close", False)
        assert get_quality_policy(db).gates_close is False

    def test_corrupt_mode_falls_back_to_basic(self, db):
        _set(db, "quality_mode", "banana")
        assert get_quality_policy(db).mode is QualityMode.BASIC

    def test_non_bool_gate_is_not_enabled(self, db):
        _set(db, "quality_mode", "full")
        _set(db, "quality_gate_close", "true")  # JSON string, not boolean
        assert get_quality_policy(db).gates_close is False


class TestSettingValidators:
    def test_quality_mode_accepts_valid(self):
        for mode in ("off", "basic", "full"):
            assert _validate_quality_mode(mode) == mode

    @pytest.mark.parametrize("bad", ["Full", "", "none", 5, None, ["full"]])
    def test_quality_mode_rejects_invalid(self, bad):
        with pytest.raises(ValueError):
            _validate_quality_mode(bad)

    def test_bool_validator(self):
        assert _validate_bool(True) is True
        assert _validate_bool(False) is False

    @pytest.mark.parametrize("bad", ["true", 1, 0, None, "false"])
    def test_bool_validator_rejects_non_bool(self, bad):
        with pytest.raises(ValueError):
            _validate_bool(bad)


class TestQualityPolicyEndpoint:
    def test_default_policy(self, client):
        r = client.get(POLICY)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mode"] == "basic"
        assert body["surfaces_enabled"] is True
        assert body["plan_driven"] is False
        assert body["gates_close"] is False

    def test_reflects_full_mode_with_gate(self, client, db):
        _set(db, "quality_mode", "full")
        _set(db, "quality_gate_close", True)
        body = client.get(POLICY).json()
        assert body["mode"] == "full"
        assert body["plan_driven"] is True
        assert body["gates_close"] is True

    def test_off_mode(self, client, db):
        _set(db, "quality_mode", "off")
        body = client.get(POLICY).json()
        assert body["mode"] == "off"
        assert body["surfaces_enabled"] is False

    def test_requires_auth(self, unauthed_client):
        assert unauthed_client.get(POLICY).status_code == 401
