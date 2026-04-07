#!/bin/bash
# docker-entrypoint.sh — Container startup script.
# Bridges the license key to the generic plugin system:
#   FILAOPS_LICENSE_KEY → download wheel → set FILAOPS_PRO_MODULE
#
# Core's Python code only reads FILAOPS_PRO_MODULE (generic).
# This shell script is the only place that knows about the license
# server URL and PRO-specific download logic.

set -e

# ─── PRO Plugin Auto-Download ───
if [ -n "$FILAOPS_LICENSE_KEY" ]; then
    LICENSE_URL="${LICENSE_SERVER_URL:-https://license.blb3dprinting.com}"

    if ! python -c "import filaops_pro" 2>/dev/null; then
        echo "FilaOps: License key detected. Downloading PRO plugin..."
        WHEEL_PATH="/tmp/filaops_pro-0.1.0-py3-none-any.whl"

        if curl -sf -H "X-License-Key: $FILAOPS_LICENSE_KEY" \
            "$LICENSE_URL/api/v1/download/filaops-pro" \
            -o "$WHEEL_PATH"; then
            pip install --no-cache-dir "$WHEEL_PATH" 2>&1 | tail -1
            rm -f "$WHEEL_PATH"
            echo "FilaOps: PRO plugin installed."
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
    exec env FILAOPS_PRO_MODULE="$FILAOPS_PRO_MODULE" uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'
fi
