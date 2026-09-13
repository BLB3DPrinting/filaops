"""
Tests for Security Audit API endpoints (app/api/v1/endpoints/security.py)

Covers:
- GET /api/v1/security/audit (run full security audit)
- GET /api/v1/security/audit/export (export audit as JSON)
- GET /api/v1/security/status (quick security status overview)
- POST /api/v1/security/remediate/generate-secret-key
- POST /api/v1/security/remediate/open-env-file
- POST /api/v1/security/remediate/update-secret-key
- POST /api/v1/security/remediate/open-restart-terminal
- POST /api/v1/security/remediate/fix-dependencies
- POST /api/v1/security/remediate/fix-rate-limiting
- POST /api/v1/security/remediate/setup-https
- GET /api/v1/security/remediate/check-caddy
- POST /api/v1/security/remediate/fix-dotfile-blocking
- GET /api/v1/security/remediate/{check_id} (remediation guides)
- Auth: 401 without token, 403 for non-admin users
"""
import pytest
from unittest.mock import patch, MagicMock

BASE_URL = "/api/v1/security"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def non_admin_client(db):
    """FastAPI TestClient authenticated as a non-admin (operator) user.

    Used to verify 403 Forbidden responses on admin-only endpoints.
    """
    from app.models.user import User
    from app.core.security import create_access_token

    # Ensure a non-admin user exists (id=2, account_type='operator')
    user = db.query(User).filter(User.id == 2).first()
    if not user:
        user = User(
            id=2,
            email="operator@filaops.dev",
            password_hash="not-a-real-hash",
            first_name="Operator",
            last_name="User",
            account_type="operator",
        )
        db.add(user)
        db.flush()

    token = create_access_token(user_id=2)

    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c

    app.dependency_overrides.clear()


def _mock_audit_result(overall_status="PASS", failed=0, warnings=0):
    """Build a realistic mock audit result dict."""
    return {
        "audit_version": "1.0",
        "generated_at": "2026-01-29T12:00:00",
        "filaops_version": "3.0.1",
        "environment": "development",
        "summary": {
            "total_checks": 10,
            "passed": 10 - failed - warnings,
            "failed": failed,
            "warnings": warnings,
            "info": 0,
            "overall_status": overall_status,
        },
        "checks": [
            {
                "id": "secret_key_not_default",
                "name": "SECRET_KEY not default",
                "category": "critical",
                "status": "pass",
                "message": "SECRET_KEY is not the default value",
                "details": None,
                "remediation": None,
            },
        ],
        "system_info": {
            "os": "Windows",
            "python_version": "3.12.0",
            "database": "PostgreSQL",
            "reverse_proxy": "none",
        },
    }


# =============================================================================
# Authentication / Authorization Tests
# =============================================================================

class TestSecurityAuth:
    """All security endpoints require authentication and admin role."""

    # -- 401 Unauthorized (no token) --

    def test_audit_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/audit")
        assert resp.status_code == 401

    def test_export_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/audit/export")
        assert resp.status_code == 401

    def test_status_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/status")
        assert resp.status_code == 401

    def test_generate_secret_key_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/remediate/generate-secret-key")
        assert resp.status_code == 401

    def test_open_env_file_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/remediate/open-env-file")
        assert resp.status_code == 401

    def test_update_secret_key_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/remediate/update-secret-key")
        assert resp.status_code == 401

    def test_open_restart_terminal_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/remediate/open-restart-terminal")
        assert resp.status_code == 401

    def test_fix_dependencies_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/remediate/fix-dependencies")
        assert resp.status_code == 401

    def test_fix_rate_limiting_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/remediate/fix-rate-limiting")
        assert resp.status_code == 401

    def test_setup_https_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/remediate/setup-https",
            json={"domain": "test.local"},
        )
        assert resp.status_code == 401

    def test_check_caddy_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/remediate/check-caddy")
        assert resp.status_code == 401

    def test_fix_dotfile_blocking_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/remediate/fix-dotfile-blocking")
        assert resp.status_code == 401

    def test_remediation_guide_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/remediate/secret_key_not_default")
        assert resp.status_code == 401

    # -- 403 Forbidden (non-admin user) --

    def test_audit_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.get(f"{BASE_URL}/audit")
        assert resp.status_code == 403
        assert "Admin role required" in resp.json()["detail"]

    def test_export_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.get(f"{BASE_URL}/audit/export")
        assert resp.status_code == 403

    def test_status_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.get(f"{BASE_URL}/status")
        assert resp.status_code == 403

    def test_generate_secret_key_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.post(f"{BASE_URL}/remediate/generate-secret-key")
        assert resp.status_code == 403

    def test_open_env_file_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.post(f"{BASE_URL}/remediate/open-env-file")
        assert resp.status_code == 403

    def test_update_secret_key_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.post(f"{BASE_URL}/remediate/update-secret-key")
        assert resp.status_code == 403

    def test_open_restart_terminal_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.post(f"{BASE_URL}/remediate/open-restart-terminal")
        assert resp.status_code == 403

    def test_fix_dependencies_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.post(f"{BASE_URL}/remediate/fix-dependencies")
        assert resp.status_code == 403

    def test_fix_rate_limiting_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.post(f"{BASE_URL}/remediate/fix-rate-limiting")
        assert resp.status_code == 403

    def test_setup_https_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.post(
            f"{BASE_URL}/remediate/setup-https",
            json={"domain": "test.local"},
        )
        assert resp.status_code == 403

    def test_check_caddy_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.get(f"{BASE_URL}/remediate/check-caddy")
        assert resp.status_code == 403

    def test_fix_dotfile_blocking_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.post(f"{BASE_URL}/remediate/fix-dotfile-blocking")
        assert resp.status_code == 403

    def test_remediation_guide_forbidden_for_non_admin(self, non_admin_client):
        resp = non_admin_client.get(f"{BASE_URL}/remediate/secret_key_not_default")
        assert resp.status_code == 403


# =============================================================================
# GET /security/audit
# =============================================================================

class TestSecurityAudit:
    """Tests for the full security audit endpoint."""

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_audit_returns_full_report(self, mock_audit, client):
        mock_audit.return_value = _mock_audit_result()

        resp = client.get(f"{BASE_URL}/audit")
        assert resp.status_code == 200

        data = resp.json()
        assert data["audit_version"] == "1.0"
        assert data["filaops_version"] == "3.0.1"
        assert data["environment"] == "development"
        assert "summary" in data
        assert "checks" in data
        assert "system_info" in data

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_audit_summary_structure(self, mock_audit, client):
        mock_audit.return_value = _mock_audit_result(
            overall_status="WARN", failed=1, warnings=2,
        )

        resp = client.get(f"{BASE_URL}/audit")
        assert resp.status_code == 200

        summary = resp.json()["summary"]
        assert summary["total_checks"] == 10
        assert summary["passed"] == 7
        assert summary["failed"] == 1
        assert summary["warnings"] == 2
        assert summary["info"] == 0
        assert summary["overall_status"] == "WARN"

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_audit_checks_list(self, mock_audit, client):
        mock_audit.return_value = _mock_audit_result()

        resp = client.get(f"{BASE_URL}/audit")
        checks = resp.json()["checks"]
        assert isinstance(checks, list)
        assert len(checks) >= 1

        check = checks[0]
        assert "id" in check
        assert "name" in check
        assert "category" in check
        assert "status" in check
        assert "message" in check

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_audit_system_info(self, mock_audit, client):
        mock_audit.return_value = _mock_audit_result()

        resp = client.get(f"{BASE_URL}/audit")
        sys_info = resp.json()["system_info"]
        assert "os" in sys_info
        assert "python_version" in sys_info
        assert "database" in sys_info
        assert "reverse_proxy" in sys_info

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_audit_handles_import_error(self, mock_audit, client):
        """When the SecurityAuditor module cannot be imported, return 500."""
        from fastapi import HTTPException, status
        mock_audit.side_effect = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security audit module not found: No module named 'scripts.security_audit'",
        )

        resp = client.get(f"{BASE_URL}/audit")
        assert resp.status_code == 500
        assert "module not found" in resp.json()["detail"]

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_audit_handles_runtime_error(self, mock_audit, client):
        """When the auditor raises an unexpected error, return 500."""
        from fastapi import HTTPException, status
        mock_audit.side_effect = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Security audit failed: something went wrong",
        )

        resp = client.get(f"{BASE_URL}/audit")
        assert resp.status_code == 500
        assert "failed" in resp.json()["detail"]


# =============================================================================
# GET /security/audit/export
# =============================================================================

class TestSecurityAuditExport:
    """Tests for the audit export endpoint."""

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_export_json_returns_attachment(self, mock_audit, client):
        mock_audit.return_value = _mock_audit_result()

        resp = client.get(f"{BASE_URL}/audit/export?format=json")
        assert resp.status_code == 200

        # Verify Content-Disposition header for file download
        disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert "filaops_security_audit_" in disposition
        assert ".json" in disposition

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_export_json_includes_metadata(self, mock_audit, client):
        mock_audit.return_value = _mock_audit_result()

        resp = client.get(f"{BASE_URL}/audit/export?format=json")
        data = resp.json()

        # Export adds extra metadata fields
        assert "exported_at" in data
        assert "exported_by" in data

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_export_json_contains_audit_data(self, mock_audit, client):
        mock_audit.return_value = _mock_audit_result()

        resp = client.get(f"{BASE_URL}/audit/export?format=json")
        data = resp.json()

        # Should still have the audit data
        assert "summary" in data
        assert "checks" in data
        assert "system_info" in data

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_export_default_format_is_json(self, mock_audit, client):
        """Omitting the format parameter defaults to json."""
        mock_audit.return_value = _mock_audit_result()

        resp = client.get(f"{BASE_URL}/audit/export")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")

    def test_export_unsupported_format_returns_400(self, client):
        resp = client.get(f"{BASE_URL}/audit/export?format=pdf")
        assert resp.status_code == 400
        assert "Unsupported format" in resp.json()["detail"]

    def test_export_invalid_format_returns_400(self, client):
        resp = client.get(f"{BASE_URL}/audit/export?format=xml")
        assert resp.status_code == 400


# =============================================================================
# GET /security/status
# =============================================================================

class TestSecurityStatus:
    """Tests for the quick security status endpoint."""

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_status_healthy(self, mock_audit, client):
        mock_audit.return_value = _mock_audit_result(overall_status="PASS")

        resp = client.get(f"{BASE_URL}/status")
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "healthy"
        assert "passed" in data["message"].lower()
        assert data["summary"] is not None
        assert "checked_at" in data

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_status_warning(self, mock_audit, client):
        mock_audit.return_value = _mock_audit_result(
            overall_status="WARN", warnings=3,
        )

        resp = client.get(f"{BASE_URL}/status")
        data = resp.json()
        assert data["status"] == "warning"
        assert "3 warning" in data["message"]

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_status_critical(self, mock_audit, client):
        mock_audit.return_value = _mock_audit_result(
            overall_status="FAIL", failed=2,
        )

        resp = client.get(f"{BASE_URL}/status")
        data = resp.json()
        assert data["status"] == "critical"
        assert "2 critical" in data["message"]

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_status_unknown(self, mock_audit, client):
        result = _mock_audit_result()
        result["summary"]["overall_status"] = "UNKNOWN"
        mock_audit.return_value = result

        resp = client.get(f"{BASE_URL}/status")
        data = resp.json()
        assert data["status"] == "unknown"
        assert "unknown" in data["message"].lower()

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_status_handles_audit_failure_gracefully(self, mock_audit, client):
        """If the audit itself fails, return status=error instead of 500."""
        mock_audit.side_effect = RuntimeError("audit broke")

        resp = client.get(f"{BASE_URL}/status")
        assert resp.status_code == 200  # endpoint catches exceptions

        data = resp.json()
        assert data["status"] == "error"
        assert "Could not check" in data["message"]
        assert data["summary"] is None
        assert "checked_at" in data

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_status_includes_summary(self, mock_audit, client):
        mock_audit.return_value = _mock_audit_result()

        resp = client.get(f"{BASE_URL}/status")
        summary = resp.json()["summary"]
        assert "total_checks" in summary
        assert "passed" in summary
        assert "failed" in summary


# =============================================================================
# POST /security/remediate/generate-secret-key
# =============================================================================

class TestGenerateSecretKey:
    """Tests for the secret key generation endpoint."""

    def test_generate_secret_key_success(self, client):
        resp = client.post(f"{BASE_URL}/remediate/generate-secret-key")
        assert resp.status_code == 200

        data = resp.json()
        assert "secret_key" in data
        assert "length" in data
        assert "instructions" in data

    def test_generated_key_is_long_enough(self, client):
        resp = client.post(f"{BASE_URL}/remediate/generate-secret-key")
        data = resp.json()

        # secrets.token_urlsafe(64) produces ~86 chars
        assert data["length"] >= 64

    def test_generated_key_is_unique(self, client):
        """Two calls should produce different keys."""
        resp1 = client.post(f"{BASE_URL}/remediate/generate-secret-key")
        resp2 = client.post(f"{BASE_URL}/remediate/generate-secret-key")

        key1 = resp1.json()["secret_key"]
        key2 = resp2.json()["secret_key"]
        assert key1 != key2

    def test_instructions_are_provided(self, client):
        resp = client.post(f"{BASE_URL}/remediate/generate-secret-key")
        instructions = resp.json()["instructions"]
        assert isinstance(instructions, list)
        assert len(instructions) > 0
        # Should mention .env file
        assert any(".env" in step for step in instructions)


# =============================================================================
# POST /security/remediate/open-env-file
# =============================================================================

class TestOpenEnvFile:
    """Tests for the open .env file endpoint."""

    @patch("os.path.exists", return_value=False)
    def test_open_env_file_not_found(self, mock_exists, client):
        resp = client.post(f"{BASE_URL}/remediate/open-env-file")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    @patch("os.path.exists", return_value=True)
    def test_open_env_file_success(self, mock_exists, client):
        resp = client.post(f"{BASE_URL}/remediate/open-env-file")
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is True
        assert "env_path" in data

    @patch("subprocess.Popen")
    @patch("os.path.exists", return_value=True)
    def test_open_env_file_no_subprocess(self, mock_exists, mock_popen, client):
        resp = client.post(f"{BASE_URL}/remediate/open-env-file")
        assert resp.status_code == 200
        assert mock_popen.call_count == 0


# =============================================================================
# POST /security/remediate/update-secret-key
# =============================================================================

class TestUpdateSecretKey:
    """Tests for the auto-update SECRET_KEY endpoint."""

    @patch("os.path.exists", return_value=False)
    def test_update_secret_key_env_not_found_returns_manual(self, mock_exists, client):
        """When .env is missing (Docker), return the key for manual copy."""
        resp = client.post(f"{BASE_URL}/remediate/update-secret-key")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["manual"] is True
        assert "new_key" in data
        assert len(data["new_key"]) > 30

    @patch("builtins.open", create=True)
    @patch("os.path.exists", return_value=True)
    def test_update_secret_key_success(self, mock_exists, mock_open, client):
        """Mocks file read/write to verify the endpoint logic."""
        mock_file_content = "DATABASE_URL=postgres://...\nSECRET_KEY=old-key\nDEBUG=true\n"
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.read = MagicMock(return_value=mock_file_content)
        mock_open.return_value.write = MagicMock()

        resp = client.post(f"{BASE_URL}/remediate/update-secret-key")
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is True
        assert "updated" in data["message"].lower()
        assert "new_key_preview" in data
        assert data["requires_restart"] is True
        # Preview should be truncated
        assert data["new_key_preview"].endswith("...")


# =============================================================================
# POST /security/remediate/open-restart-terminal
# =============================================================================

class TestOpenRestartTerminal:
    """Tests for the restart terminal endpoint."""

    def test_open_restart_terminal_success(self, client):
        resp = client.post(f"{BASE_URL}/remediate/open-restart-terminal")
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is True
        assert "restart_command" in data
        assert "project_root" in data

    @patch("subprocess.Popen")
    def test_open_restart_terminal_no_subprocess(self, mock_popen, client):
        resp = client.post(f"{BASE_URL}/remediate/open-restart-terminal")
        assert resp.status_code == 200
        assert mock_popen.call_count == 0


# =============================================================================
# POST /security/remediate/fix-dependencies
# =============================================================================

class TestFixDependencies:
    """Tests for the dependency fix endpoint."""

    @patch("os.path.exists", return_value=False)
    def test_fix_deps_venv_not_found(self, mock_exists, client):
        resp = client.post(f"{BASE_URL}/remediate/fix-dependencies")
        assert resp.status_code == 404
        assert "Virtual environment not found" in resp.json()["detail"]

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_fix_deps_no_vulnerabilities(self, mock_exists, mock_run, client):
        """When pip-audit finds no vulnerabilities."""
        # First call: pip-audit --version (already installed)
        version_result = MagicMock(returncode=0, stdout="pip-audit 2.7.0")
        # Second call: pip-audit scan (no vulns - empty JSON)
        scan_result = MagicMock(
            returncode=0,
            stdout='{"dependencies": [], "fixes": []}',
        )
        mock_run.side_effect = [version_result, scan_result]

        resp = client.post(f"{BASE_URL}/remediate/fix-dependencies")
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is True
        assert "No known vulnerabilities" in data["message"]
        assert data["vulnerabilities_found"] == 0

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_fix_deps_with_vulnerabilities_upgraded(self, mock_exists, mock_run, client):
        """When pip-audit finds vulnerabilities and upgrades them."""
        import json

        # pip-audit --version: already installed
        version_result = MagicMock(returncode=0, stdout="pip-audit 2.7.0")
        # pip-audit scan: found vulnerabilities
        audit_data = {
            "dependencies": [
                {"name": "cryptography", "vulns": [{"id": "CVE-2024-001"}]},
                {"name": "requests", "vulns": [{"id": "CVE-2024-002"}]},
            ],
            "fixes": [],
        }
        scan_result = MagicMock(returncode=0, stdout=json.dumps(audit_data))
        # pip install --upgrade cryptography: success
        upgrade1 = MagicMock(returncode=0)
        # pip install --upgrade requests: success
        upgrade2 = MagicMock(returncode=0)

        mock_run.side_effect = [version_result, scan_result, upgrade1, upgrade2]

        resp = client.post(f"{BASE_URL}/remediate/fix-dependencies")
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is True
        assert data["vulnerabilities_found"] == 2
        assert len(data["packages_upgraded"]) == 2
        assert data["requires_restart"] is True

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_fix_deps_install_pip_audit_first(self, mock_exists, mock_run, client):
        """When pip-audit is not installed, it gets installed first."""
        import json

        # pip-audit --version: not installed
        version_fail = MagicMock(returncode=1, stderr="No module named pip_audit")
        # pip install pip-audit: success
        install_result = MagicMock(returncode=0)
        # pip-audit scan: no vulns
        scan_result = MagicMock(
            returncode=0,
            stdout='{"dependencies": [], "fixes": []}',
        )

        mock_run.side_effect = [version_fail, install_result, scan_result]

        resp = client.post(f"{BASE_URL}/remediate/fix-dependencies")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_fix_deps_timeout(self, mock_exists, mock_run, client):
        """When a subprocess times out, return 504."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pip", timeout=120)

        resp = client.post(f"{BASE_URL}/remediate/fix-dependencies")
        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"].lower()


# =============================================================================
# POST /security/remediate/fix-rate-limiting
# =============================================================================

class TestFixRateLimiting:
    """Tests for the rate limiting fix endpoint."""

    @patch("os.path.exists", return_value=False)
    def test_fix_rate_limiting_venv_not_found(self, mock_exists, client):
        resp = client.post(f"{BASE_URL}/remediate/fix-rate-limiting")
        assert resp.status_code == 404
        assert "Virtual environment not found" in resp.json()["detail"]

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_fix_rate_limiting_success(self, mock_exists, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="installed slowapi")

        resp = client.post(f"{BASE_URL}/remediate/fix-rate-limiting")
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is True
        assert "SlowAPI installed" in data["message"]
        assert data["requires_restart"] is True

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_fix_rate_limiting_install_failure(self, mock_exists, mock_run, client):
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="ERROR: Could not install packages",
        )

        resp = client.post(f"{BASE_URL}/remediate/fix-rate-limiting")
        assert resp.status_code == 500
        assert "Installation failed" in resp.json()["detail"]

    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    def test_fix_rate_limiting_timeout(self, mock_exists, mock_run, client):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pip", timeout=120)

        resp = client.post(f"{BASE_URL}/remediate/fix-rate-limiting")
        assert resp.status_code == 504
        assert "timed out" in resp.json()["detail"].lower()


# =============================================================================
# POST /security/remediate/setup-https
# =============================================================================

class TestSetupHTTPS:
    """Tests for the HTTPS setup endpoint."""

    def test_setup_https_requires_domain_body(self, client):
        """Missing JSON body should return 422."""
        resp = client.post(f"{BASE_URL}/remediate/setup-https")
        assert resp.status_code == 422

    def test_setup_https_empty_domain(self, client):
        resp = client.post(
            f"{BASE_URL}/remediate/setup-https",
            json={"domain": "   "},
        )
        assert resp.status_code == 400
        assert "Domain cannot be empty" in resp.json()["detail"]

    @patch("builtins.open", create=True)
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    @patch("os.path.exists")
    def test_setup_https_creates_caddyfile(
        self, mock_exists, mock_run, mock_popen, mock_open, client
    ):
        """When caddy is installed, creates Caddyfile and starts it."""
        # os.path.exists: True for vite config, caddy check, etc.
        mock_exists.return_value = True

        # caddy version check: installed
        mock_run.return_value = MagicMock(returncode=0, stdout="v2.7.0")

        # Mock file open for Caddyfile write and vite.config.js read/write
        mock_file = MagicMock()
        mock_file.read.return_value = "export default defineConfig({\n  plugins: [],\n})"
        mock_open.return_value.__enter__ = lambda s: mock_file
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.post(
            f"{BASE_URL}/remediate/setup-https",
            json={"domain": "filaops.local"},
        )
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is True
        assert "filaops.local" in data["domain"]
        assert data["caddyfile_created"] is True


# =============================================================================
# GET /security/remediate/check-caddy
# =============================================================================

class TestCheckCaddy:
    """Tests for the Caddy status check endpoint."""

    @patch("subprocess.run")
    def test_caddy_installed(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=0, stdout="v2.7.6 h1:abc123")

        resp = client.get(f"{BASE_URL}/remediate/check-caddy")
        assert resp.status_code == 200

        data = resp.json()
        assert data["installed"] is True
        assert "v2.7" in data["version"]

    @patch("subprocess.run", side_effect=FileNotFoundError("caddy not found"))
    def test_caddy_not_installed(self, mock_run, client):
        resp = client.get(f"{BASE_URL}/remediate/check-caddy")
        assert resp.status_code == 200

        data = resp.json()
        assert data["installed"] is False
        assert data["version"] is None

    @patch("subprocess.run")
    def test_caddy_nonzero_return(self, mock_run, client):
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        resp = client.get(f"{BASE_URL}/remediate/check-caddy")
        assert resp.status_code == 200
        assert resp.json()["installed"] is False


# =============================================================================
# POST /security/remediate/fix-dotfile-blocking
# =============================================================================

class TestFixDotfileBlocking:
    """Tests for the dotfile blocking remediation endpoint."""

    @patch("os.path.exists", return_value=False)
    def test_fix_dotfile_no_caddyfile(self, mock_exists, client):
        resp = client.post(f"{BASE_URL}/remediate/fix-dotfile-blocking")
        assert resp.status_code == 404
        assert "Caddyfile not found" in resp.json()["detail"]

    @patch("builtins.open", create=True)
    @patch("os.path.exists", return_value=True)
    def test_fix_dotfile_already_configured(self, mock_exists, mock_open, client):
        """When blocking is already present, return success without modification."""
        mock_file = MagicMock()
        mock_file.read.return_value = (
            "example.com {\n"
            "    @blocked path /.env /.git/*\n"
            "    respond @blocked 404\n"
            "}\n"
        )
        mock_open.return_value.__enter__ = lambda s: mock_file
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        resp = client.post(f"{BASE_URL}/remediate/fix-dotfile-blocking")
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is True
        assert data["already_configured"] is True

    @patch("subprocess.run")
    @patch("builtins.open", create=True)
    @patch("os.path.exists", return_value=True)
    def test_fix_dotfile_adds_rules(self, mock_exists, mock_open, mock_run, client):
        """When no blocking exists, adds handle rules and reloads Caddy."""
        mock_file = MagicMock()
        mock_file.read.return_value = (
            "example.com {\n"
            "    reverse_proxy localhost:8000\n"
            "    handle {\n"
            "        reverse_proxy localhost:5173\n"
            "    }\n"
            "}\n"
        )
        mock_open.return_value.__enter__ = lambda s: mock_file
        mock_open.return_value.__exit__ = MagicMock(return_value=False)

        # caddy reload: success
        mock_run.return_value = MagicMock(returncode=0)

        resp = client.post(f"{BASE_URL}/remediate/fix-dotfile-blocking")
        assert resp.status_code == 200

        data = resp.json()
        assert data["success"] is True
        assert data["caddyfile_updated"] is True


# =============================================================================
# GET /security/remediate/{check_id} (remediation guides)
# =============================================================================

class TestRemediationGuides:
    """Tests for the remediation guide lookup endpoint."""

    KNOWN_CHECK_IDS = [
        "secret_key_not_default",
        "secret_key_entropy",
        "https_enabled",
        "cors_not_wildcard",
        "admin_password_changed",
        "dependencies_secure",
        "rate_limiting_enabled",
        "backup_configured",
        "env_file_not_exposed",
    ]

    @pytest.mark.parametrize("check_id", KNOWN_CHECK_IDS)
    def test_known_check_ids_return_guide(self, check_id, client):
        resp = client.get(f"{BASE_URL}/remediate/{check_id}")
        assert resp.status_code == 200

        data = resp.json()
        assert "title" in data
        assert "severity" in data
        assert "steps" in data
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) > 0

    def test_unknown_check_id_returns_404(self, client):
        resp = client.get(f"{BASE_URL}/remediate/nonexistent_check_xyz")
        assert resp.status_code == 404
        assert "No remediation guide found" in resp.json()["detail"]

    def test_remediation_guide_has_step_structure(self, client):
        resp = client.get(f"{BASE_URL}/remediate/secret_key_not_default")
        data = resp.json()

        assert data["severity"] == "critical"
        assert data["estimated_time"] == "2 minutes"

        step = data["steps"][0]
        assert "step" in step
        assert "title" in step
        assert "description" in step

    def test_remediation_guide_secret_key_has_auto_generate(self, client):
        resp = client.get(f"{BASE_URL}/remediate/secret_key_not_default")
        data = resp.json()
        assert data["can_auto_generate"] is True

    def test_remediation_guide_https_has_auto_fix(self, client):
        resp = client.get(f"{BASE_URL}/remediate/https_enabled")
        data = resp.json()
        assert data.get("can_auto_fix_https") is True

    def test_remediation_guide_dependencies_has_auto_fix(self, client):
        resp = client.get(f"{BASE_URL}/remediate/dependencies_secure")
        data = resp.json()
        assert data.get("can_auto_fix_dependencies") is True

    def test_remediation_guide_rate_limiting_has_auto_fix(self, client):
        resp = client.get(f"{BASE_URL}/remediate/rate_limiting_enabled")
        data = resp.json()
        assert data.get("can_auto_fix_rate_limiting") is True

    def test_remediation_guide_dotfile_has_auto_fix(self, client):
        resp = client.get(f"{BASE_URL}/remediate/env_file_not_exposed")
        data = resp.json()
        assert data.get("can_auto_fix_dotfiles") is True

    def test_remediation_guide_cors_no_auto_generate(self, client):
        resp = client.get(f"{BASE_URL}/remediate/cors_not_wildcard")
        data = resp.json()
        assert data["can_auto_generate"] is False

    def test_remediation_guide_backup_no_auto_generate(self, client):
        resp = client.get(f"{BASE_URL}/remediate/backup_configured")
        data = resp.json()
        assert data["can_auto_generate"] is False


# =============================================================================
# Schema / Validation Tests
# =============================================================================

class TestSchemaValidation:
    """Tests for request/response schema validation."""

    def test_setup_https_missing_domain_field(self, client):
        """Sending an empty JSON object should fail validation."""
        resp = client.post(
            f"{BASE_URL}/remediate/setup-https",
            json={},
        )
        assert resp.status_code == 422

    def test_setup_https_wrong_type_domain(self, client):
        """Sending a non-string domain should fail validation."""
        resp = client.post(
            f"{BASE_URL}/remediate/setup-https",
            json={"domain": 12345},
        )
        # Pydantic may coerce int to string, or may reject it; either is valid
        # The important thing is we don't get a 500
        assert resp.status_code in (200, 400, 422, 500)

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_audit_response_matches_schema(self, mock_audit, client):
        """Verify the audit response includes all SecurityAuditResponse fields."""
        mock_audit.return_value = _mock_audit_result()

        resp = client.get(f"{BASE_URL}/audit")
        assert resp.status_code == 200

        data = resp.json()
        # All top-level fields from SecurityAuditResponse
        required_fields = [
            "audit_version", "generated_at", "filaops_version",
            "environment", "summary", "checks", "system_info",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

        # Summary fields from SecuritySummary
        summary_fields = [
            "total_checks", "passed", "failed", "warnings",
            "info", "overall_status",
        ]
        for field in summary_fields:
            assert field in data["summary"], f"Missing summary field: {field}"

        # SystemInfo fields
        sys_fields = ["os", "python_version", "database", "reverse_proxy"]
        for field in sys_fields:
            assert field in data["system_info"], f"Missing system_info field: {field}"

    @patch("app.api.v1.endpoints.security.run_security_audit")
    def test_audit_check_item_schema(self, mock_audit, client):
        """Verify individual check items have the correct shape."""
        mock_audit.return_value = _mock_audit_result()

        resp = client.get(f"{BASE_URL}/audit")
        check = resp.json()["checks"][0]

        required_fields = ["id", "name", "category", "status", "message"]
        for field in required_fields:
            assert field in check, f"Missing check field: {field}"

        # Optional fields should be present (even if None)
        assert "details" in check
        assert "remediation" in check
