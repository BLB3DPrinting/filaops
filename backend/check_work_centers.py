"""Check production_orders table structure"""
from sqlalchemy import inspect
from app.db.session import engine

try:
    inspector = inspect(engine)
    print("production_orders columns:")
    for col in inspector.get_columns('production_orders'):
        print(f"  {col['name']}")
except Exception as e:
    print(f"Error: {e}")
