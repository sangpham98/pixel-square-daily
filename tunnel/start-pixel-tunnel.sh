#!/usr/bin/env bash
set -euo pipefail

# Cloudflare Quick Tunnel with auto-sync Telegram webhook URL.
# Extracts the tunnel URL from cloudflared output and updates the Telegram webhook.

CF="${CLOUDFLARED_BIN:-$(command -v cloudflared || true)}"
APP_URL="${WEBHOOK_LOCAL_URL:-http://127.0.0.1:8096}"
LOG_FILE="${TUNNEL_LOG_FILE:-./tunnel/cloudflared.log}"
ENV_FILE="${ENV_FILE:-./.env}"

if [[ -z "$CF" ]]; then
  echo "cloudflared not found. Set CLOUDFLARED_BIN=/path/to/cloudflared" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG_FILE")"

SYNCED=0

# Start cloudflared and capture URL from output
"$CF" tunnel --url "$APP_URL" --no-autoupdate 2>&1 | while IFS= read -r line; do
  echo "$line" | tee -a "$LOG_FILE"

  # Extract quick tunnel URL (only sync once per startup)
  if [[ $SYNCED -eq 0 && "$line" =~ (https://[a-z0-9-]+\.trycloudflare\.com) ]]; then
    TUNNEL_URL="${BASH_REMATCH[1]}"
    echo "[tunnel-sync] Detected URL: $TUNNEL_URL" >&2

    # Update .env file
    if [[ -f "$ENV_FILE" ]]; then
      sed -i "s|^WEBHOOK_PUBLIC_URL=.*|WEBHOOK_PUBLIC_URL=${TUNNEL_URL}|" "$ENV_FILE"
      echo "[tunnel-sync] Updated .env WEBHOOK_PUBLIC_URL" >&2
    fi

    # Update Telegram webhook
    (
      cd "$(dirname "$ENV_FILE")"
      .venv/bin/python -c "
import os, sys, requests
from dotenv import load_dotenv
load_dotenv()
token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
if not token:
    print('[tunnel-sync] No TELEGRAM_BOT_TOKEN, skipping', file=sys.stderr)
    sys.exit(0)
url = '${TUNNEL_URL}/telegram/webhook'
secret = os.environ.get('TELEGRAM_WEBHOOK_SECRET', '')
payload = {'url': url, 'allowed_updates': '[\"message\",\"callback_query\"]'}
if secret:
    payload['secret_token'] = secret
r = requests.post(f'https://api.telegram.org/bot{token}/setWebhook', data=payload, timeout=20)
print(f'[tunnel-sync] Webhook set to {url}: {r.text}', file=sys.stderr)
" 2>&1
    ) | tee -a "$LOG_FILE"

    SYNCED=1
  fi
done
