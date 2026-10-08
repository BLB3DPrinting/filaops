"""GHSA-r4j7-j592-gchw: production refuses to start with the compose default key.

Each case imports ``app.main`` in a fresh interpreter, which is what uvicorn
does before serving, with ENVIRONMENT=production. The settings check runs at
import time, so a placeholder SECRET_KEY must stop the process there, and a
random key must let the import finish.

No network: psycopg's connect is replaced before the import, so the one
database read app.main makes at import time (PRO CORS origins, which falls
back on any error) fails at once instead of opening a socket. The startup
connectivity check runs in the lifespan, which an import does not start.
"""
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]

# docker-compose.yml: SECRET_KEY: ${SECRET_KEY:-change-in-production}
COMPOSE_DEFAULT_SECRET_KEY = "change-in-production"

# Not a DB_PASSWORD placeholder, so only SECRET_KEY can trip the guard.
UNUSED_DATABASE_URL = "postgresql+psycopg://filaops:startup-guard-test@127.0.0.1:1/filaops"

IMPORT_APP_OFFLINE = """
import psycopg

def _offline(*args, **kwargs):
    raise psycopg.OperationalError("startup guard test: no database")

psycopg.connect = _offline
psycopg.Connection.connect = _offline
import app.main
"""


def _import_app_in_production(secret_key):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("SECRET_KEY", "DB_", "DATABASE_URL", "ENVIRONMENT"))
    }
    env.update(
        ENVIRONMENT="production",
        SECRET_KEY=secret_key,
        DATABASE_URL=UNUSED_DATABASE_URL,
        DEBUG="false",
    )
    return subprocess.run(
        [sys.executable, "-c", IMPORT_APP_OFFLINE],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_production_refuses_compose_default_secret_key():
    result = _import_app_in_production(COMPOSE_DEFAULT_SECRET_KEY)

    assert result.returncode != 0, "app imported in production with the compose default SECRET_KEY"
    assert "Refusing to start in production" in result.stderr
    assert "SECRET_KEY" in result.stderr.split("Refusing to start in production", 1)[1]


@pytest.mark.parametrize("secret_key", [secrets.token_hex(32)], ids=["random"])
def test_production_starts_with_random_secret_key(secret_key):
    result = _import_app_in_production(secret_key)

    assert result.returncode == 0, result.stderr[-2000:]
    assert "Refusing to start in production" not in result.stderr
