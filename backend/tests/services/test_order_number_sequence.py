from datetime import datetime, timezone
from app.services.sales_order_service import generate_order_number


def test_order_number_sequence_crossing_1000(db, make_sales_order):
    """Verify order number generation does not duplicate when crossing #999 to #1000."""
    year = datetime.now(timezone.utc).year

    # Seed order 999
    make_sales_order(order_number=f"SO-{year}-999")

    # Next order should be 1000
    next_order_num = generate_order_number(db)
    assert next_order_num == f"SO-{year}-1000"

    # Seed order 1000
    make_sales_order(order_number=next_order_num)

    # Next order should be 1001 (not 1000 again)
    next_order_num_2 = generate_order_number(db)
    assert next_order_num_2 == f"SO-{year}-1001"
