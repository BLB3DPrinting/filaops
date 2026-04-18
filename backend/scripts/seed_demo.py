"""
FilaOps demo seed — deterministic rich demo dataset.

Usage:
    python -m scripts.seed_demo            # interactive
    python -m scripts.seed_demo --yes      # CI / Docker (no prompt)
    python -m scripts.seed_demo --dry-run  # print plan, rollback
    python -m scripts.seed_demo --seed 42  # override seed

See backend/scripts/README.md for full documentation.
"""
import argparse
import os
import sys
import time
from pathlib import Path

# Make `app.*` imports work when invoked as `python -m scripts.seed_demo`
# from the backend/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

from scripts.seed_data import _guards, _time  # noqa: E402


# Ordered pipeline. Each entry is (label, module_name, callable_name).
# Modules are added commit-by-commit as they land.
SEED_PIPELINE: list[tuple[str, str, str]] = [
    ("Creating users...", "users", "seed"),
    ("Creating printers + maintenance...", "printers", "seed"),
    ("Creating price levels...", "price_levels", "seed"),
    ("Creating customers...", "customers", "seed"),
    ("Creating vendors...", "vendors", "seed"),
    ("Creating products + BOMs + routings...", "products", "seed"),
    ("Creating inventory state...", "inventory", "seed"),
    ("Creating quotes...", "quotes", "seed"),
    ("Creating 90 days of sales...", "sales_orders", "seed"),
    ("Creating 90 days of production...", "production", "seed"),
    # ("Creating 90 days of purchasing...", "purchasing", "seed"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed the FilaOps demo database.")
    parser.add_argument("--yes", action="store_true", help="skip wipe confirmation prompt")
    parser.add_argument("--dry-run", action="store_true", help="run pipeline then roll back")
    parser.add_argument(
        "--seed",
        type=int,
        default=int(os.environ.get("FILAOPS_DEMO_SEED", 42)),
        help="deterministic RNG seed (default 42 or $FILAOPS_DEMO_SEED)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print(f"[seed] Target database: {settings.DB_NAME}")
    _guards.check_db_name(settings.DB_NAME)
    _guards.check_alembic_head()
    _guards.confirm_wipe(settings.DB_NAME, args.yes)

    _time.initialize(args.seed)

    print("[seed] Wiping tables...")
    db = SessionLocal()
    t_start = time.time()
    try:
        _guards.wipe_all_tables(db)

        context: dict = {
            "seed": args.seed,
            "dry_run": args.dry_run,
            "admin_email": "admin@acme-demo.test",
            "admin_password": "demo1234",
        }

        for label, module_name, fn_name in SEED_PIPELINE:
            print(f"[seed] {label}")
            module = __import__(f"scripts.seed_data.{module_name}", fromlist=[fn_name])
            fn = getattr(module, fn_name)
            fn(db, context)

        if args.dry_run:
            print("[seed] --dry-run — rolling back.")
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    elapsed = time.time() - t_start
    print(f"[seed] Done in {elapsed:.1f}s.")
    print()
    print(f"[seed] Login: {context['admin_email']} / {context['admin_password']}")
    print(
        "[seed] Price levels created (A/B/C/D). Customer assignment is a PRO "
        "feature --"
    )
    print(
        "[seed]   install filaops-pro to assign customers to tiers."
    )
    print(f"[seed] Open: http://localhost:5173")
    return 0


if __name__ == "__main__":
    sys.exit(main())
