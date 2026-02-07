# check_payments.py - run from backend folder with: python check_payments.py
from app.db.session import SessionLocal
from app.models.payment import Payment

try:
    with SessionLocal() as db:
        payments = db.query(Payment).order_by(Payment.payment_date.desc()).limit(5).all()
        print('Recent payments:')
        for p in payments:
            print(f'  {p.payment_number}: date={p.payment_date}, status={p.status}, type={p.payment_type}')
except Exception as e:
    print(f"Error: {e}")
