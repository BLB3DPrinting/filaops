"""Backfill quotes.expires_at and enforce NOT NULL + server_default

Context
-------
Online quotes are valid for 90 days. The Core ``Quote`` model has
historically declared ``expires_at`` as ``nullable=False``, but the
column on the live database has been ``NULL``-able due to a missing
migration. PRO's public quoter route (``calculate_quote``) constructed
``Quote(...)`` rows without supplying ``expires_at``, so every
quoter-SPA quote landed with ``NULL``. A single such row was enough to
500 the entire ``GET /api/v1/quotes/`` list endpoint via Pydantic
response validation.

This migration is the structural cure (paired with code-level fixes in
the PRO route and a ``server_default`` on the Core model):

1. Backfill any existing ``NULL`` rows with ``created_at + 90 days``
   (matches the business rule for online quotes).
2. Attach a server-side default of ``now() + interval '90 days'`` so
   future raw INSERTs that forget to set ``expires_at`` still land a
   sensible value.
3. Tighten the column to ``NOT NULL`` so a bug like this fails at the
   database boundary (IntegrityError on insert) instead of silently
   poisoning the list endpoint.

Safe to run repeatedly: each step is guarded against the current state.

Revision ID: 083
Revises: 082
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa


revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "quotes" not in set(inspector.get_table_names()):
        # Fresh install path: the table will be created by an earlier
        # migration in its target shape. Nothing to do here.
        return

    cols = {c["name"]: c for c in inspector.get_columns("quotes")}
    if "expires_at" not in cols:
        # Defensive: schema drift we don't recognize. Bail rather than
        # silently invent the column with a guessed type.
        return

    # 1. Backfill NULLs using created_at + 90 days. created_at is
    # NOT NULL with server_default=now(), so this is always safe.
    op.execute(
        sa.text(
            "UPDATE quotes "
            "SET expires_at = created_at + interval '90 days' "
            "WHERE expires_at IS NULL"
        )
    )

    # 2. Attach server_default and 3. enforce NOT NULL in one alter.
    op.alter_column(
        "quotes",
        "expires_at",
        existing_type=sa.DateTime(timezone=False),
        nullable=False,
        server_default=sa.text("(now() + interval '90 days')"),
    )


def downgrade() -> None:
    # Reverse: drop the server_default and relax NOT NULL. We do NOT
    # null out the backfilled values — losing real expiration dates on
    # a downgrade would be worse than the original bug.
    op.alter_column(
        "quotes",
        "expires_at",
        existing_type=sa.DateTime(timezone=False),
        nullable=True,
        server_default=None,
    )
