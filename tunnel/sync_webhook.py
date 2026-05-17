#!/usr/bin/env python3
"""Start cloudflared quick tunnel and auto-sync Telegram webhook URL on change."""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).parent.parent
ENV_FILE = PROJECT_DIR / ".env"
LOG_FILE = Path(__file__).parent / "cloudflared.log"


def update_webhook(tunnel_url: str) -> None:
    """Update Telegram webhook to the new tunnel URL."""
    load_dotenv(ENV_FILE, override=True)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("[sync] No TELEGRAM_BOT_TOKEN, skipping webhook update", file=sys.stderr)
        return

    webhook_url = f"{tunnel_url}/telegram/webhook"
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    payload = {"url": webhook_url, "allowed_updates": '["message","callback_query"]'}
    if secret:
        payload["secret_token"] = secret

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            data=payload,
            timeout=20,
        )
        print(f"[sync] Webhook set to {webhook_url}: {r.text}", file=sys.stderr)
    except Exception as exc:
        print(f"[sync] Failed to set webhook: {exc}", file=sys.stderr)


def update_env(tunnel_url: str) -> None:
    """Update WEBHOOK_PUBLIC_URL in .env file."""
    if not ENV_FILE.exists():
        return
    text = ENV_FILE.read_text(encoding="utf-8")
    new_text = re.sub(
        r"^WEBHOOK_PUBLIC_URL=.*$",
        f"WEBHOOK_PUBLIC_URL={tunnel_url}",
        text,
        flags=re.MULTILINE,
    )
    ENV_FILE.write_text(new_text, encoding="utf-8")
    print(f"[sync] Updated .env WEBHOOK_PUBLIC_URL={tunnel_url}", file=sys.stderr)


def main() -> None:
    cloudflared = os.environ.get("CLOUDFLARED_BIN", "cloudflared")
    app_url = os.environ.get("WEBHOOK_LOCAL_URL", "http://127.0.0.1:8096")

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [cloudflared, "tunnel", "--url", app_url, "--no-autoupdate"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    url_pattern = re.compile(r"(https://[a-z0-9-]+\.trycloudflare\.com)")
    synced = False

    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.rstrip()
            print(line)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")

            if not synced:
                m = url_pattern.search(line)
                if m:
                    tunnel_url = m.group(1)
                    print(f"[sync] Detected URL: {tunnel_url}", file=sys.stderr)
                    update_env(tunnel_url)
                    update_webhook(tunnel_url)
                    synced = True
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    main()
