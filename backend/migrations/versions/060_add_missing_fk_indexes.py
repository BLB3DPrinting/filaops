"""Add missing foreign key indexes for query performance.

Adds indexes on FK columns that are frequently used in WHERE clauses
but were missing index=True in their model definitions.

Tables affected:
- purchase_orders.vendor_id
- purchase_order_lines.purchase_order_id
- purchase_order_lines.product_id
- resources.work_center_id
- routing_operations.routing_id
- routing_operations.work_center_id
"""
from alembic import op


revision = '060'
down_revision = '059'
branch_labels = None
depends_on = None


def upgrade():
    # Purchase orders — vendor lookup
    op.create_index(
        'ix_purchase_orders_vendor_id',
        'purchase_orders', ['vendor_id'],
        if_not_exists=True,
    )

    # Purchase order lines — parent PO lookup + product lookup
    op.create_index(
        'ix_purchase_order_lines_purchase_order_id',
        'purchase_order_lines', ['purchase_order_id'],
        if_not_exists=True,
    )
    op.create_index(
        'ix_purchase_order_lines_product_id',
        'purchase_order_lines', ['product_id'],
        if_not_exists=True,
    )

    # Resources — work center filtering for scheduling
    op.create_index(
        'ix_resources_work_center_id',
        'resources', ['work_center_id'],
        if_not_exists=True,
    )

    # Routing operations — routing lookup + work center scheduling
    op.create_index(
        'ix_routing_operations_routing_id',
        'routing_operations', ['routing_id'],
        if_not_exists=True,
    )
    op.create_index(
        'ix_routing_operations_work_center_id',
        'routing_operations', ['work_center_id'],
        if_not_exists=True,
    )


def downgrade():
    op.drop_index('ix_routing_operations_work_center_id', table_name='routing_operations')
    op.drop_index('ix_routing_operations_routing_id', table_name='routing_operations')
    op.drop_index('ix_resources_work_center_id', table_name='resources')
    op.drop_index('ix_purchase_order_lines_product_id', table_name='purchase_order_lines')
    op.drop_index('ix_purchase_order_lines_purchase_order_id', table_name='purchase_order_lines')
    op.drop_index('ix_purchase_orders_vendor_id', table_name='purchase_orders')
