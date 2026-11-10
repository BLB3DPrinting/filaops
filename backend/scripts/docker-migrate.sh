#!/bin/bash
# docker-migrate.sh — Safe migration wrapper for Docker containers.
# PRO plugin is already installed by the entrypoint before this runs.

set -e

echo "FilaOps: Running database migrations..."

# Check if alembic can find the current DB revision.
CURRENT_OUTPUT=$(alembic current 2>&1) || true

if echo "$CURRENT_OUTPUT" | grep -q "Can't locate revision"; then
    echo ""
    echo "================================================================"
    echo "  DATABASE MIGRATION MISMATCH DETECTED"
    echo "================================================================"
    echo ""
    echo "  Your database was last upgraded by a newer version of FilaOps"
    echo "  than the one starting now, or by a version whose migrations"
    echo "  this one does not have. This version cannot use it, so the"
    echo "  migrate step has stopped. Nothing has been changed or deleted."
    echo ""
    echo "  Alembic reports (the database is on a revision this version"
    echo "  does not know):"
    echo ""
    # alembic prints the revision twice (a log line and a FAILED line).
    # Show the text once, without the log prefix.
    echo "$CURRENT_OUTPUT" | grep -o "Can't locate revision.*" | sort -u | sed 's/^/    /'
    echo ""
    echo "  Your data is still in the database. If you went back to an"
    echo "  older version after upgrading, do one of these:"
    echo ""
    echo "    1. Check out the newer version again (the one you ran before"
    echo "       going back), then rebuild and start it:"
    echo ""
    echo "         git checkout <newer version>"
    echo "         docker compose up --build -d"
    echo ""
    echo "    2. Or restore the database backup you took before you"
    echo "       upgraded. Follow section 3 of docs/ROLLBACK.md:"
    echo "       https://blb3dprinting.github.io/filaops/ROLLBACK/"
    echo "       Anything entered after that backup was taken is not in it."
    echo ""
    echo "  LAST RESORT, only for a database you do not need (a test install):"
    echo "  removing the database volume DELETES ALL DATA in it, for good."
    echo ""
    echo "    docker compose down"
    echo "    docker volume rm filaops_pgdata"
    echo "    docker compose up --build -d"
    echo "================================================================"
    echo ""
    exit 1
fi

# Core migrations
alembic upgrade head

# PRO plugin migrations (if installed by entrypoint)
if python -c "import filaops_pro" 2>/dev/null; then
    PRO_INI=$(python -c "import filaops_pro, os; print(os.path.join(os.path.dirname(filaops_pro.__file__), 'alembic.ini'))")
    if [ -f "$PRO_INI" ]; then
        echo "FilaOps: Running PRO plugin migrations..."
        alembic -c "$PRO_INI" upgrade head
        echo "FilaOps: PRO migrations complete."
    fi
fi

echo "FilaOps: Migrations complete."
