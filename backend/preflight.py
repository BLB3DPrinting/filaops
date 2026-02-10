from importlib import util as _util

def have(modname: str) -> bool:
    try:
        # supports dotted modules (e.g., "email_validator")
        return _util.find_spec(modname) is not None
    except Exception:
        return False

mods = [
    # core runtime
    "sqlalchemy", "fastapi", "alembic", "uvicorn",
    # config & validation
    "pydantic", "pydantic_settings", "email_validator",
    # auth & forms
    "jwt", "cryptography", "multipart",
    # requests
    "requests",
    # Postgres driver
    "psycopg2"
]

missing = [m for m in mods if not have(m)]
print("Missing:", missing if missing else "None")
