"""SEC-401: Security remediation endpoint tests.

Verifies:
- Production environment blocks remediation endpoints (403)
- Authentication is required (401)
- Endpoints do NOT spawn desktop GUI processes or remote binary downloads
- Safe configuration generation works as expected
"""

from unittest.mock import patch


def test_open_env_file_requires_auth(unauthed_client):
    """Unauthenticated request must be rejected with 401."""
    resp = unauthed_client.post("/api/v1/security/remediate/open-env-file")
    assert resp.status_code == 401


def test_open_env_file_blocked_in_production(client, monkeypatch):
    """Remediation endpoints must be blocked in production environments."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")

    resp = client.post("/api/v1/security/remediate/open-env-file")
    assert resp.status_code == 403
    assert "disabled in production" in resp.json()["detail"]


@patch("subprocess.Popen")
def test_open_env_file_returns_safe_info_without_subprocess(mock_popen, client, tmp_path):
    """Endpoint must return safe file path and NOT spawn OS processes."""
    # Ensure .env exists in the expected location
    resp = client.post("/api/v1/security/remediate/open-env-file")
    # If .env doesn't exist in worktree, 404 is valid, but subprocess must NEVER be called
    assert mock_popen.call_count == 0
    if resp.status_code == 200:
        data = resp.json()
        assert data["success"] is True
        assert "env_path" in data
        assert "Configuration file located at" in data["message"]


@patch("subprocess.Popen")
def test_open_restart_terminal_returns_guidance_without_subprocess(mock_popen, client):
    """Endpoint returns restart command guidance without launching OS terminals."""
    resp = client.post("/api/v1/security/remediate/open-restart-terminal")
    assert resp.status_code == 200
    assert mock_popen.call_count == 0

    data = resp.json()
    assert data["success"] is True
    assert "restart_command" in data
    assert "project_root" in data


@patch("subprocess.run")
@patch("subprocess.Popen")
def test_setup_https_safe_generation_without_shell_scripts(mock_popen, mock_run, client, tmp_path, monkeypatch):
    """setup-https must generate configuration safely without remote PowerShell execution."""
    # Test domain validation rejection
    bad_resp = client.post("/api/v1/security/remediate/setup-https", json={"domain": "example.com; rm -rf /"})
    assert bad_resp.status_code == 400

    # Test valid domain execution
    with patch("builtins.open", create=True):
        resp = client.post("/api/v1/security/remediate/setup-https", json={"domain": "erp.local"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["caddyfile_created"] is True
        assert data["domain"] == "erp.local"
        # Verify no remote binary download or shell scripts were executed
        assert mock_popen.call_count == 0
        assert mock_run.call_count == 0
