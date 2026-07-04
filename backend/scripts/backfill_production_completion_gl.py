"""
Backfill production-completion GL entries (#880).

Historical production completions posted inventory transactions but no
journal entries, so Raw Materials (1200) was never relieved and Finished
Goods (1220) carries a credit balance. This script posts the missing
completion entries using the SAME production code the app now runs at
completion time (app.services.production_gl_service), backdated to each
production order's completed_at date.

Usage:
    # Dry run (DEFAULT — prints per-PO journal-entry previews, writes nothing)
    python scripts/backfill_production_completion_gl.py

    # Apply for real. REFUSES to run unless --backup-marker points to a
    # file touched within the last 24 hours (the ops runbook creates the
    # marker right after pg_dump). Writes a JSON manifest of created
    # journal entries for scripted rollback.
    python scripts/backfill_production_completion_gl.py --apply \
        --backup-marker /root/backups/pg_dump.marker \
        --manifest backfill_manifest.json

    # Roll back a previous apply: voids every journal entry in the
    # manifest and unlinks its inventory transactions so a later apply
    # can re-post them.
    python scripts/backfill_production_completion_gl.py --rollback backfill_manifest.json

    # Optionally restrict to specific production orders
    python scripts/backfill_production_completion_gl.py --po-id 3 --po-id 5

Idempotency: posting sweeps only inventory transactions with
journal_entry_id IS NULL, so re-running --apply after a successful run
posts nothing.
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

# Allow running as `python scripts/backfill_production_completion_gl.py`
# from the backend directory (or anywhere else).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.models.accounting import GLJournalEntry  # noqa: E402
from app.models.inventory import InventoryTransaction  # noqa: E402
from app.models.production_order import ProductionOrder  # noqa: E402
from app.services.production_gl_service import (  # noqa: E402
    compute_completion_gl_preview,
    create_production_completion_gl_entry,
    find_unjournaled_production_order_ids,
)

BACKUP_MARKER_MAX_AGE_HOURS = 24


class BackupMarkerError(RuntimeError):
    """--apply was requested without a fresh backup marker."""


def _load_candidate_orders(
    db: Session, po_ids: Optional[List[int]] = None
) -> List[ProductionOrder]:
    candidate_ids = find_unjournaled_production_order_ids(db, po_ids)
    if not candidate_ids:
        return []
    return (
        db.query(ProductionOrder)
        .filter(ProductionOrder.id.in_(candidate_ids))
        .order_by(ProductionOrder.id)
        .all()
    )


def _entry_date_for(order: ProductionOrder) -> date:
    """Backdate to the order's completion date (owner decision); today if unset."""
    if order.completed_at:
        return order.completed_at.date()
    return date.today()


def _print_preview(order: ProductionOrder, preview, out=print) -> None:
    out(f"\nPO#{order.code} (id={order.id}, status={order.status}, "
        f"entry_date={_entry_date_for(order).isoformat()})")
    out(f"  swept transactions: {len(preview.transaction_ids)} "
        f"(ids {preview.transaction_ids})")
    out(f"  M_mat  (CR 1200): {preview.material_cost}")
    out(f"  M_pkg  (CR 1230): {preview.packaging_cost}")
    out(f"  M_labor(CR 5100): {preview.labor_cost}")
    out(f"  FG     (DR 1220): {preview.finished_goods_value}")
    out(f"  S (scrap 1210 credits): {preview.scrap_wip_credits}")
    out(f"  V = FG + S - M = {preview.variance}")
    if preview.lines:
        out("  journal entry lines:")
        for account_code, amount, dr_cr in preview.lines:
            out(f"    {dr_cr} {account_code}  {amount}")
    else:
        out("  (all swept rows zero-cost — nothing would be posted)")


def check_backup_marker(backup_marker: Optional[str]) -> None:
    """Raise BackupMarkerError unless the marker file exists and is fresh."""
    if not backup_marker:
        raise BackupMarkerError(
            "--apply requires --backup-marker <path> pointing to a file "
            "created right after the pg_dump backup."
        )
    marker = Path(backup_marker)
    if not marker.is_file():
        raise BackupMarkerError(f"Backup marker not found: {backup_marker}")
    mtime = datetime.fromtimestamp(marker.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - mtime
    if age > timedelta(hours=BACKUP_MARKER_MAX_AGE_HOURS):
        raise BackupMarkerError(
            f"Backup marker {backup_marker} is {age} old (max "
            f"{BACKUP_MARKER_MAX_AGE_HOURS}h). Take a fresh pg_dump and "
            "touch the marker again."
        )


def run_dry_run(db: Session, po_ids: Optional[List[int]] = None, out=print) -> list:
    """Print per-PO previews. Posts nothing, writes nothing."""
    orders = _load_candidate_orders(db, po_ids)
    if not orders:
        out("No production orders with unjournaled consumption/receipt "
            "transactions found. Nothing to backfill.")
        return []

    out(f"DRY RUN — {len(orders)} production order(s) with sweepable rows. "
        "No changes will be made.")
    previews = []
    totals = {
        "material": 0, "packaging": 0, "labor": 0,
        "fg": 0, "scrap": 0, "variance": 0, "txns": 0,
    }
    for order in orders:
        preview = compute_completion_gl_preview(db, order)
        if preview is None:
            continue
        _print_preview(order, preview, out=out)
        previews.append((order, preview))
        totals["material"] += preview.material_cost
        totals["packaging"] += preview.packaging_cost
        totals["labor"] += preview.labor_cost
        totals["fg"] += preview.finished_goods_value
        totals["scrap"] += preview.scrap_wip_credits
        totals["variance"] += preview.variance
        totals["txns"] += len(preview.transaction_ids)

    out("\n=== TOTALS ===")
    out(f"  transactions swept: {totals['txns']}")
    out(f"  materials (CR 1200): {totals['material']}")
    out(f"  packaging (CR 1230): {totals['packaging']}")
    out(f"  labor     (CR 5100): {totals['labor']}")
    out(f"  finished goods (DR 1220): {totals['fg']}")
    out(f"  scrap 1210 credits (S): {totals['scrap']}")
    out(f"  net variance (5200; positive = credit): {totals['variance']}")
    out("\nRun again with --apply --backup-marker <path> to post.")
    return previews


def run_apply(
    db: Session,
    manifest_path: str,
    backup_marker: Optional[str],
    po_ids: Optional[List[int]] = None,
    out=print,
) -> list:
    """Post completion entries for every candidate order; write the manifest.

    All entries post in ONE transaction — any failure rolls back everything.
    The manifest (JSON) records created journal-entry ids and per-PO amounts
    for --rollback.
    """
    check_backup_marker(backup_marker)

    orders = _load_candidate_orders(db, po_ids)
    if not orders:
        out("Nothing to backfill — no unjournaled production "
            "consumption/receipt transactions found.")
        return []

    manifest_entries = []
    for order in orders:
        entry_date = _entry_date_for(order)
        preview = compute_completion_gl_preview(db, order)
        journal_entry = create_production_completion_gl_entry(
            db, order, user_id=None, entry_date=entry_date
        )
        if journal_entry is None:
            out(f"PO#{order.code}: skipped (zero-cost rows only)")
            continue
        _print_preview(order, preview, out=out)
        out(f"  -> POSTED {journal_entry.entry_number} "
            f"(journal_entry_id={journal_entry.id}, entry_date={entry_date})")
        manifest_entries.append({
            "production_order_id": order.id,
            "production_order_code": order.code,
            "journal_entry_id": journal_entry.id,
            "entry_number": journal_entry.entry_number,
            "entry_date": entry_date.isoformat(),
            "material_cost": str(preview.material_cost),
            "packaging_cost": str(preview.packaging_cost),
            "labor_cost": str(preview.labor_cost),
            "finished_goods_value": str(preview.finished_goods_value),
            "scrap_wip_credits": str(preview.scrap_wip_credits),
            "variance": str(preview.variance),
            "transaction_ids": preview.transaction_ids,
        })

    db.commit()

    if not manifest_entries:
        out("Nothing was posted (all candidates zero-cost).")
        return []

    manifest = {
        "script": "backfill_production_completion_gl",
        "issue": "#880",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "entries": manifest_entries,
    }
    Path(manifest_path).write_text(json.dumps(manifest, indent=2))
    out(f"\nPosted {len(manifest_entries)} journal entr(ies). "
        f"Manifest written to {manifest_path} — keep it for --rollback.")
    return manifest_entries


def run_rollback(db: Session, manifest_path: str, out=print) -> int:
    """Void every journal entry in the manifest and unlink its transactions.

    Unlinking (journal_entry_id back to NULL) restores the pre-apply state
    so the sweep can re-post after the rollback; voided entries disappear
    from the posted-only reports (#880 PR-1).
    """
    manifest = json.loads(Path(manifest_path).read_text())
    entries = manifest.get("entries", [])
    if not entries:
        out(f"Manifest {manifest_path} contains no entries — nothing to roll back.")
        return 0

    voided = 0
    for item in entries:
        je_id = item["journal_entry_id"]
        journal_entry = db.query(GLJournalEntry).filter(
            GLJournalEntry.id == je_id
        ).first()
        if journal_entry is None:
            out(f"  journal entry {je_id} not found — skipping")
            continue
        if journal_entry.status == "voided":
            out(f"  {journal_entry.entry_number} already voided — skipping")
            continue
        journal_entry.status = "voided"
        journal_entry.voided_at = datetime.now(timezone.utc)
        journal_entry.void_reason = (
            "Rollback of #880 production-completion GL backfill "
            f"(manifest applied {manifest.get('applied_at', 'unknown')})"
        )
        unlinked = db.query(InventoryTransaction).filter(
            InventoryTransaction.journal_entry_id == je_id
        ).update({"journal_entry_id": None}, synchronize_session="fetch")
        out(f"  voided {journal_entry.entry_number} "
            f"(PO#{item.get('production_order_code')}), "
            f"unlinked {unlinked} transaction(s)")
        voided += 1

    db.commit()
    out(f"Rolled back {voided} journal entr(ies) from {manifest_path}.")
    return voided


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill production-completion GL entries (#880). "
                    "Dry-run by default."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply", action="store_true",
        help="Post the journal entries for real (requires --backup-marker).",
    )
    mode.add_argument(
        "--rollback", metavar="MANIFEST",
        help="Void the journal entries listed in a previous apply's manifest.",
    )
    parser.add_argument(
        "--backup-marker", metavar="PATH",
        help="File touched right after pg_dump; must be < 24h old for --apply.",
    )
    parser.add_argument(
        "--manifest", metavar="PATH",
        default=f"backfill_production_completion_gl_manifest_"
                f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
        help="Where --apply writes the rollback manifest.",
    )
    parser.add_argument(
        "--po-id", type=int, action="append", dest="po_ids",
        help="Restrict to specific production order id(s); repeatable.",
    )
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        if args.rollback:
            run_rollback(db, args.rollback)
        elif args.apply:
            try:
                run_apply(
                    db,
                    manifest_path=args.manifest,
                    backup_marker=args.backup_marker,
                    po_ids=args.po_ids,
                )
            except BackupMarkerError as exc:
                print(f"REFUSING TO APPLY: {exc}", file=sys.stderr)
                return 2
        else:
            run_dry_run(db, po_ids=args.po_ids)
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
