"""
Create adjustment_reasons table and seed default data.

Provides configurable reasons for inventory adjustments,
similar to scrap_reasons for production scrapping.

Revision ID: 058_adjustment_reasons
Revises: 057_seed_scrap_reasons
Create Date: 2026-02-08
"""
from alembic import op
from sqlalchemy import text

# revision identifiers
revision = '058_adjustment_reasons'
down_revision = '057_seed_scrap_reasons'
branch_labels = None
depends_on = None


def upgrade():
    """Create adjustment_reasons table and seed default data."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS adjustment_reasons (
            id SERIAL PRIMARY KEY,
            code VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            active BOOLEAN DEFAULT TRUE NOT NULL,
            sequence INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW() NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW() NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_adjustment_reasons_code ON adjustment_reasons (code);
        CREATE INDEX IF NOT EXISTS ix_adjustment_reasons_id ON adjustment_reasons (id);
    """)

    op.execute("""
        INSERT INTO adjustment_reasons (code, name, description, sequence) VALUES
        ('physical_count', 'Physical Count', 'Discrepancy found during physical inventory count', 10),
        ('cycle_count', 'Cycle Count', 'Adjustment from cycle counting process', 20),
        ('correction', 'Data Correction', 'Correcting a data entry error', 30),
        ('damaged', 'Damaged Goods', 'Item damaged in storage or handling', 40),
        ('found', 'Found Inventory', 'Previously unaccounted inventory discovered', 50),
        ('theft_loss', 'Theft/Loss', 'Inventory missing due to theft or unexplained loss', 60),
        ('expired', 'Expired/Obsolete', 'Item past usable life or obsolete', 70),
        ('reclassification', 'Reclassification', 'Item moved to different category or account', 80),
        ('other', 'Other', 'Other adjustment reason - specify in notes', 90)
        ON CONFLICT (code) DO NOTHING;
    """)


def downgrade():
    """Drop adjustment_reasons table."""
    op.execute("DROP TABLE IF EXISTS adjustment_reasons;")
