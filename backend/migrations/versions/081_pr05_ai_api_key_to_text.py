"""Widen company_settings.ai_api_key to TEXT for encrypted storage (PR-05).

PR-05 introduces app.core.crypto.EncryptedString, a TypeDecorator that stores
Fernet ciphertext in place of plaintext. Fernet output is roughly 1.5x the
plaintext length plus ~57 bytes of overhead (version byte, timestamp, IV,
HMAC, then URL-safe base64). A VARCHAR(500) column therefore only fits about
303 bytes of plaintext — fine for current Anthropic API keys (~108 chars) but
a footgun for future longer secrets (Shopify/QBO OAuth tokens in PR-06+).

Switching to TEXT removes the size cap so EncryptedString can be used safely
on any sensitive column without per-call sizing math.

Revision ID: 081
Revises: 080
Create Date: 2026-05-05
"""
from alembic import op
import sqlalchemy as sa


revision = "081"
down_revision = "080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres VARCHAR(N) -> TEXT is a metadata-only change (no table rewrite).
    op.alter_column(
        "company_settings",
        "ai_api_key",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    # NOTE: this can fail if a row contains an encrypted ai_api_key whose
    # ciphertext exceeds 500 chars — which is exactly why we widened the
    # column. Operators rolling back must clear or shorten the value first.
    op.alter_column(
        "company_settings",
        "ai_api_key",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=True,
    )
