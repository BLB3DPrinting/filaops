"""GHSA-r4j7-j592-gchw: a public placeholder SECRET_KEY must never sign accepted tokens.

The stock docker-compose.yml ships ``SECRET_KEY: ${SECRET_KEY:-change-in-production}``.
Outside production the app used that public value as-is, so anyone could forge
an admin JWT. This test builds Settings the way the app does at startup with
that compose default in a non-production environment, makes the security
module use the resulting key (it copies settings.SECRET_KEY at import time),
then sends a token forged with the PUBLIC placeholder to GET /api/v1/auth/me.
Expected: 401.

"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

# Exact default from docker-compose.yml: SECRET_KEY: ${SECRET_KEY:-change-in-production}
COMPOSE_DEFAULT_SECRET_KEY = "change-in-production"


def _forge_admin_token(user_id: int, key: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "exp": now + timedelta(minutes=30),
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, key, algorithm="HS256")


@pytest.mark.parametrize("environment", ["development", "staging"])
def test_forged_admin_token_signed_with_compose_placeholder_is_refused(
    unauthed_client, db, monkeypatch, environment
):
    from app.core import security
    from app.core.settings import Settings
    from app.models.user import User

    admin = User(
        email=f"a2-admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        account_type="admin",
        status="active",
    )
    db.add(admin)
    db.flush()

    # Control: a token signed with the running (test) key is accepted, so a
    # 401 below can only come from the key being refused.
    good = security.create_access_token(user_id=admin.id)
    ok = unauthed_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {good}"}
    )
    assert ok.status_code == 200, ok.text

    # Settings as the stock compose install would produce them, non-production.
    cfg = Settings(
        _env_file=None,
        ENVIRONMENT=environment,
        SECRET_KEY=COMPOSE_DEFAULT_SECRET_KEY,
    )
    # app.core.security copies settings.SECRET_KEY at import; mirror that.
    monkeypatch.setattr(security, "SECRET_KEY", cfg.SECRET_KEY)

    forged = _forge_admin_token(admin.id, COMPOSE_DEFAULT_SECRET_KEY)
    resp = unauthed_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}
    )
    assert resp.status_code == 401, (
        f"forged admin token signed with the public placeholder "
        f"{COMPOSE_DEFAULT_SECRET_KEY!r} was ACCEPTED in ENVIRONMENT={environment}: "
        f"status={resp.status_code} body={resp.text[:200]}"
    )
