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
    PRO_INSTALL_FAILED=0

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
                PRO_INSTALL_FAILED=1
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
                # mktemp -d makes the directory 0700; the app reads it as appuser.
                chmod -R a+rX /app/portal-dist
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

    # Bridge: set the generic plugin env var so Core's load_plugin finds it.
    # A failed pip run can still leave a partial, importable package behind
    # (e.g. a dependency missing); never load it after a reported failure.
    if [ "$PRO_INSTALL_FAILED" -eq 0 ] && python -c "import filaops_pro" 2>/dev/null; then
        FILAOPS_PRO_MODULE=filaops_pro
    fi
fi

# ─── Drop Root ───
# Everything above may need root (pip into the system site-packages, writing
# /app/portal-dist). Everything below runs as appuser. The directories the app
# writes to can be bind mounts or volumes created by root, or by a release
# that ran as root, so hand them to appuser first. If one still is not
# writable (some host filesystems ignore chown), keep running as root rather
# than break uploads or the instance identity, and say so.
APP_USER=appuser
APP_GROUP=appgroup
RUN_AS=()
# Only inside the image: appuser does not exist when the script runs elsewhere.
if [ "$(id -u)" = "0" ] && id "$APP_USER" >/dev/null 2>&1; then
    WRITABLE_DIRS=(/app/uploads /app/logs /app/static "${LICENSE_CONFIG_DIR:-/var/lib/filaops/config}")
    for var in UPLOAD_DIR STATIC_DIR UPLOAD_PRODUCTS_DIR UPLOAD_PO_DOCS_DIR UPLOAD_QC_PHOTOS_DIR; do
        if [ -n "${!var}" ]; then
            WRITABLE_DIRS+=("${!var}")
        fi
    done

    DROP_TO=(setpriv --reuid="$APP_USER" --regid="$APP_GROUP" --init-groups env "HOME=/home/$APP_USER")
    UNWRITABLE=""
    for dir in "${WRITABLE_DIRS[@]}"; do
        mkdir -p "$dir" 2>/dev/null || true
        # -h: change a symlink itself, never the file it points to.
        find "$dir" \! -user "$APP_USER" -exec chown -h "$APP_USER:$APP_GROUP" {} + 2>/dev/null || true
        if ! "${DROP_TO[@]}" test -w "$dir"; then
            UNWRITABLE="$UNWRITABLE '$dir'"
        fi
    done
    if [ -d /app/portal-dist ]; then
        chmod -R a+rX /app/portal-dist
    fi

    if [ -z "$UNWRITABLE" ]; then
        RUN_AS=("${DROP_TO[@]}")
    else
        echo "FilaOps: WARNING: $APP_USER cannot write to:$UNWRITABLE" >&2
        echo "FilaOps: WARNING: running as root. Make these writable by uid $(id -u "$APP_USER") to fix." >&2
    fi
fi

# ─── Run Command ───
if [ $# -gt 0 ]; then
    exec "${RUN_AS[@]}" env FILAOPS_PRO_MODULE="$FILAOPS_PRO_MODULE" "$@"
else
    # ─── Database Migrations ───
    # Only run on the default uvicorn startup path. Custom commands (e.g. the
    # migrate service running docker-migrate.sh) handle their own migrations with
    # full error recovery and PRO plugin migration steps.
    echo "FilaOps: Running database migrations..."
    "${RUN_AS[@]}" python -m alembic upgrade head
    echo "FilaOps: Migrations complete."
    exec "${RUN_AS[@]}" env FILAOPS_PRO_MODULE="$FILAOPS_PRO_MODULE" uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'
fi
