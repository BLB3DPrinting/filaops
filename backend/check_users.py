# check_users.py - run from backend folder with: python check_users.py
from app.db.session import SessionLocal
from app.models.user import User

try:
    with SessionLocal() as db:
        users = db.query(User).limit(5).all()
        for u in users:
            print(f'{u.id}: {u.email} ({u.account_type})')
except Exception as e:
    print(f"Error: {e}")
