#!/bin/sh
# Inject runtime config so the frontend can reach the backend
# regardless of how the image was built.
cat > /usr/share/nginx/html/config.js << EOF
window.__MYCEL_CONFIG__ = { apiBase: "${API_BASE:-}" };
EOF
exec nginx -g "daemon off;"
