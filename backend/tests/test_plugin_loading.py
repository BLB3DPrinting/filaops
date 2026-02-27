"""Tests for config-driven plugin registration (main.load_plugin).

Verifies that:
- No module name → returns False, app unchanged
- Valid module with register() → register(app) called, returns True
- Missing module (ImportError) → returns False, app still works
- Broken register() (RuntimeError) → returns False, app still works
"""

import types
from unittest.mock import MagicMock, patch

from fastapi import FastAPI


from app.main import load_plugin


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

    def test_returns_false_on_import_error(self):
        app = FastAPI()
        with patch("importlib.import_module", side_effect=ImportError("not found")):
            result = load_plugin(app, module_name="nonexistent_plugin")
        assert result is False

    def test_app_still_works_after_import_error(self, client):
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

    def test_app_still_works_after_register_error(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
