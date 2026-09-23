#!/bin/bash
# docker-entrypoint.sh — Container startup script.
# Bridges the license key to the generic plugin system:
#   FILAOPS_LICENSE_KEY → download wheel → set FILAOPS_PRO_MODULE
#
# Core's Python code only reads FILAOPS_PRO_MODULE (generic).
# This shell script is the only place that knows about the license
# server URL and PRO-specific download logic.

set -e
# A pipeline fails if any stage fails, not just the last one. Without this,
# `cmd | tail -1` reports tail's success even when cmd failed.
set -o pipefail

# ─── PRO Plugin Auto-Download ───
if [ -n "$FILAOPS_LICENSE_KEY" ]; then
    LICENSE_URL="${LICENSE_SERVER_URL:-https://license.blb3dprinting.com}"

    if ! python -c "import filaops_pro" 2>/dev/null; then
        echo "FilaOps: License key detected. Downloading PRO plugin..."
        WHEEL_PATH="/tmp/filaops_pro-0.1.0-py3-none-any.whl"

        if curl -sf -H "X-License-Key: $FILAOPS_LICENSE_KEY" \
            "$LICENSE_URL/api/v1/download/filaops-pro" \
            -o "$WHEEL_PATH"; then
            # Check pip's own exit status. A failed install is handled like a
            # failed download (log it, start in Community mode) rather than
            # aborting under set -e, so Core still boots.
            PIP_LOG=$(mktemp)
            PIP_STATUS=0
            pip install --no-cache-dir "$WHEEL_PATH" >"$PIP_LOG" 2>&1 || PIP_STATUS=$?
            if [ "$PIP_STATUS" -eq 0 ]; then
                tail -n 1 "$PIP_LOG"
                echo "FilaOps: PRO plugin installed."
            else
                echo "FilaOps: ERROR: PRO plugin install failed (pip exit $PIP_STATUS). pip output:" >&2
                tail -n 20 "$PIP_LOG" >&2
                echo "FilaOps: Starting in Community mode." >&2
            fi
            rm -f "$WHEEL_PATH" "$PIP_LOG"
        else
            echo "FilaOps: Could not download PRO plugin. Check your license key."
            echo "FilaOps: Starting in Community mode."
        fi
    fi

    # ─── Portal Frontend Auto-Download ───
    if [ ! -d "/app/portal-dist" ]; then
        if curl -sf -H "X-License-Key: $FILAOPS_LICENSE_KEY" \
            "$LICENSE_URL/api/v1/download/filaops-portal" \
            -o /tmp/portal-dist.tar.gz; then
            STAGING=$(mktemp -d)
            if tar -xzf /tmp/portal-dist.tar.gz -C "$STAGING"; then
                mv "$STAGING" /app/portal-dist
                echo "FilaOps: Portal frontend installed."
            else
                echo "FilaOps: Portal archive corrupt — skipping portal install."
                rm -rf "$STAGING"
            fi
            rm -f /tmp/portal-dist.tar.gz
        else
            echo "FilaOps: Could not download portal frontend. Portal UI unavailable."
        fi
    fi

    # Bridge: set the generic plugin env var so Core's load_plugin finds it
    if python -c "import filaops_pro" 2>/dev/null; then
        FILAOPS_PRO_MODULE=filaops_pro
    fi
fi

# ─── Run Command ───
if [ $# -gt 0 ]; then
    exec env FILAOPS_PRO_MODULE="$FILAOPS_PRO_MODULE" "$@"
else
    # ─── Database Migrations ───
    # Only run on the default uvicorn startup path. Custom commands (e.g. the
    # migrate service running docker-migrate.sh) handle their own migrations with
    # full error recovery and PRO plugin migration steps.
    echo "FilaOps: Running database migrations..."
    python -m alembic upgrade head
    echo "FilaOps: Migrations complete."
    exec env FILAOPS_PRO_MODULE="$FILAOPS_PRO_MODULE" uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'
fi
