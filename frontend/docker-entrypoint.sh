#!/bin/sh
# Write runtime config for the frontend.
# This runs at container startup so the API URL can be set via environment
# variables without rebuilding the image.
#
# API_SAME_ORIGIN tells the app that the page is served by the nginx in this
# container, which proxies /api to the backend. With API_URL empty, the app
# then calls /api on the address the page was opened on, whatever the host
# name or port, instead of guessing where the backend is (src/config/api.js).
# An empty API_URL alone cannot say that: it is also what "not set" looks like.
cat > /usr/share/nginx/html/config.js << EOF
window.__FILAOPS_CONFIG__ = {
  API_URL: "${VITE_API_URL:-}",
  API_SAME_ORIGIN: true
};
EOF
exec "$@"
