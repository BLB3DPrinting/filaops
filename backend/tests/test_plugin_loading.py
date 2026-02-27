"""Tests for config-driven plugin registration (main.load_plugin).

Verifies that:
- No module name → returns False, app unchanged
- Valid module with register() → register(app) called, returns True
- Missing module (ModuleNotFoundError) → returns False, app still works
- Broken register() (RuntimeError) → returns False, app still works
- ImportError inside plugin (broken dependency) → caught as error, not "not installed"
"""

import types
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from starlette.testclient import TestClient

from app.main import load_plugin, app as real_app


class TestLoadPluginNoModule:
    """No plugin configured → community edition."""

    def test_returns_false_when_no_module(self):
        app = FastAPI()
        assert load_plugin(app, module_name=None) is False

    def test_returns_false_when_empty_string(self):
        app = FastAPI()
        assert load_plugin(app, module_name="") is False

    @patch.dict("os.environ", {"FILAOPS_PRO_MODULE": ""}, clear=False)
    def test_reads_env_var_when_no_arg(self):
        app = FastAPI()
        assert load_plugin(app) is False


class TestLoadPluginSuccess:
    """Valid plugin module with register() callable."""

    def test_register_is_called_with_app(self):
        app = FastAPI()
        mock_register = MagicMock()
        fake_plugin = types.ModuleType("fake_pro")
        fake_plugin.register = mock_register

        with patch("importlib.import_module", return_value=fake_plugin):
            result = load_plugin(app, module_name="fake_pro")

        assert result is True
        mock_register.assert_called_once_with(app)

    @patch.dict("os.environ", {"FILAOPS_PRO_MODULE": "filaops_pro"}, clear=False)
    def test_reads_module_from_env(self):
        app = FastAPI()
        mock_register = MagicMock()
        fake_plugin = types.ModuleType("filaops_pro")
        fake_plugin.register = mock_register

        with patch("importlib.import_module", return_value=fake_plugin) as mock_import:
            result = load_plugin(app)

        assert result is True
        mock_import.assert_called_once_with("filaops_pro")
        mock_register.assert_called_once_with(app)


class TestLoadPluginMissing:
    """Plugin configured but not installed → graceful degradation."""

    def test_returns_false_on_module_not_found(self):
        app = FastAPI()
        with patch("importlib.import_module", side_effect=ModuleNotFoundError("not found")):
            result = load_plugin(app, module_name="nonexistent_plugin")
        assert result is False

    def test_app_serves_requests_after_missing_plugin(self):
        """Simulate a missing plugin on the real app, then verify it still serves."""
        with patch("importlib.import_module", side_effect=ModuleNotFoundError("not found")):
            load_plugin(real_app, module_name="nonexistent_plugin")

        client = TestClient(real_app)
        resp = client.get("/")
        assert resp.status_code == 200


class TestLoadPluginBrokenRegister:
    """Plugin exists but register() raises → error logged, app survives."""

    def test_returns_false_on_register_error(self):
        app = FastAPI()
        fake_plugin = types.ModuleType("broken_plugin")
        fake_plugin.register = MagicMock(side_effect=RuntimeError("boom"))

        with patch("importlib.import_module", return_value=fake_plugin):
            result = load_plugin(app, module_name="broken_plugin")

        assert result is False

    def test_app_serves_requests_after_broken_register(self):
        """Simulate a broken register() on the real app, then verify it still serves."""
        fake_plugin = types.ModuleType("broken_plugin")
        fake_plugin.register = MagicMock(side_effect=RuntimeError("boom"))

        with patch("importlib.import_module", return_value=fake_plugin):
            load_plugin(real_app, module_name="broken_plugin")

        client = TestClient(real_app)
        resp = client.get("/")
        assert resp.status_code == 200


class TestLoadPluginInternalImportError:
    """ImportError inside plugin (broken dependency) → caught as general error, not 'not installed'."""

    def test_internal_import_error_returns_false(self):
        """An ImportError that isn't ModuleNotFoundError (e.g. broken dep inside plugin)
        should be caught by the general except, not misreported as 'not installed'."""
        app = FastAPI()
        with patch("importlib.import_module", side_effect=ImportError("cannot import name 'foo'")):
            result = load_plugin(app, module_name="plugin_with_broken_dep")
        assert result is False
