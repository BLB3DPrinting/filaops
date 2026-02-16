"""Fix product.customer_id FK to reference customers table instead of users.

The customer_id column on products is meant for B2B customer restriction,
so it should reference the customers table (not users).

Issue: https://github.com/Blb3D/filaops/issues/310
"""
from alembic import op


revision = '061'
down_revision = '060'
branch_labels = None
depends_on = None


def upgrade():
    # Drop old FK referencing users.id
    # Convention: fk_<table>_<column>_<referenced_table>
    # SQLAlchemy auto-generates constraint names; use batch mode for safety
    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_constraint(
            'fk_products_customer', type_='foreignkey'
        )
        batch_op.create_foreign_key(
            'fk_products_customer',
            'customers',
            ['customer_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_constraint(
            'fk_products_customer', type_='foreignkey'
        )
        batch_op.create_foreign_key(
            'fk_products_customer',
            'users',
            ['customer_id'],
            ['id'],
            ondelete='SET NULL',
        )
