"""Tests for config-driven plugin registration (main.load_plugin).

Verifies that:
- No module name → returns False, app unchanged
- Valid module with register() → register(app) called, returns True
- Missing module (ModuleNotFoundError) → returns False, app still works
- Missing dependency inside plugin → distinct error from "not installed"
- Plugin without register() callable → returns False
- Broken register() (RuntimeError) → returns False, app still works
"""

import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.main import load_plugin, app as real_app


@pytest.fixture(autouse=True)
def _isolate_plugin_env(monkeypatch):
    """Ensure FILAOPS_PRO_MODULE is never set during tests."""
    monkeypatch.delenv("FILAOPS_PRO_MODULE", raising=False)


class TestLoadPluginNoModule:
    """No plugin configured → community edition."""

    def test_returns_false_when_no_module(self):
        app = FastAPI()
        assert load_plugin(app, module_name=None) is False

    def test_returns_false_when_empty_string(self):
        app = FastAPI()
        assert load_plugin(app, module_name="") is False

    def test_reads_env_var_when_no_arg(self, monkeypatch):
        monkeypatch.setenv("FILAOPS_PRO_MODULE", "")
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

    def test_reads_module_from_env(self, monkeypatch):
        monkeypatch.setenv("FILAOPS_PRO_MODULE", "filaops_pro")
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

    def test_returns_false_when_plugin_itself_missing(self):
        app = FastAPI()
        exc = ModuleNotFoundError("No module named 'nonexistent'")
        exc.name = "nonexistent"
        with patch("importlib.import_module", side_effect=exc):
            result = load_plugin(app, module_name="nonexistent")
        assert result is False

    def test_returns_false_when_plugin_dependency_missing(self):
        """Plugin exists but imports a missing dependency — distinct from 'not installed'."""
        app = FastAPI()
        exc = ModuleNotFoundError("No module named 'some_dep'")
        exc.name = "some_dep"
        with patch("importlib.import_module", side_effect=exc):
            result = load_plugin(app, module_name="my_plugin")
        assert result is False

    def test_app_serves_requests_after_missing_plugin(self):
        exc = ModuleNotFoundError("not found")
        exc.name = "nonexistent"
        with patch("importlib.import_module", side_effect=exc):
            load_plugin(real_app, module_name="nonexistent")

        client = TestClient(real_app)
        resp = client.get("/")
        assert resp.status_code == 200


class TestLoadPluginNoRegisterCallable:
    """Plugin module exists but has no register() function."""

    def test_returns_false_when_no_register(self):
        app = FastAPI()
        fake_plugin = types.ModuleType("no_register_plugin")
        # Module has no register attribute at all

        with patch("importlib.import_module", return_value=fake_plugin):
            result = load_plugin(app, module_name="no_register_plugin")

        assert result is False

    def test_returns_false_when_register_not_callable(self):
        app = FastAPI()
        fake_plugin = types.ModuleType("bad_register_plugin")
        fake_plugin.register = "not a function"

        with patch("importlib.import_module", return_value=fake_plugin):
            result = load_plugin(app, module_name="bad_register_plugin")

        assert result is False


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
        fake_plugin = types.ModuleType("broken_plugin")
        fake_plugin.register = MagicMock(side_effect=RuntimeError("boom"))

        with patch("importlib.import_module", return_value=fake_plugin):
            load_plugin(real_app, module_name="broken_plugin")

        client = TestClient(real_app)
        resp = client.get("/")
        assert resp.status_code == 200


class TestLoadPluginInternalImportError:
    """Non-ModuleNotFoundError ImportError inside plugin → caught as general error."""

    def test_internal_import_error_returns_false(self):
        app = FastAPI()
        with patch("importlib.import_module", side_effect=ImportError("cannot import name 'foo'")):
            result = load_plugin(app, module_name="plugin_with_broken_dep")
        assert result is False
