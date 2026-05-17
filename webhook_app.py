from __future__ import annotations

import os
import threading
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from src.logger import log
from src.telegram_handlers import handle_update
from src.utils import env

APP_NAME = "PIXEL Spare Webhook"
APP_VERSION = "0.1.0"
STARTED_AT = time.time()
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
_recent_updates: dict[int, float] = {}
UPDATE_DEDUP_TTL = int(os.getenv("TELEGRAM_UPDATE_DEDUP_TTL", "900"))

app = FastAPI(title=APP_NAME, version=APP_VERSION)

def process_update_background(update: dict[str, Any]) -> None:
    try:
        update_id = update.get("update_id")
        kind = "callback_query" if "callback_query" in update else "message" if "message" in update else "other"
        log.debug("WEBHOOK queued update_id=%s kind=%s", update_id, kind)
        handle_update(update)
        log.debug("WEBHOOK handled update_id=%s kind=%s", update_id, kind)
    except Exception as exc:
        log.error("WEBHOOK handler error update_id=%s: %s", update.get('update_id'), exc)



def cleanup_recent_updates() -> None:
    now = time.time()
    expired = [uid for uid, ts in _recent_updates.items() if now - ts > UPDATE_DEDUP_TTL]
    for uid in expired:
        _recent_updates.pop(uid, None)


def is_duplicate(update: dict[str, Any]) -> bool:
    cleanup_recent_updates()
    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return False
    if update_id in _recent_updates:
        return True
    _recent_updates[update_id] = time.time()
    return False


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "ok": True,
        "service": APP_NAME,
        "version": APP_VERSION,
        "endpoints": ["/health", "/telegram/webhook"],
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": APP_NAME,
        "version": APP_VERSION,
        "uptime_seconds": int(time.time() - STARTED_AT),
        "bot_token_configured": bool(env("TELEGRAM_BOT_TOKEN")),
        "webhook_secret_configured": bool(WEBHOOK_SECRET),
        "auto_post": env("BINANCE_AUTO_POST_SHORT", "false").lower() in {"1", "true", "yes"},
    }


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> JSONResponse:
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    update = await request.json()
    if is_duplicate(update):
        return JSONResponse({"ok": True, "skipped": "duplicate_update"})

    # Return 200 to Telegram immediately; process the update in background.
    # Telegram marks webhook slow if we wait for sendMessage/LLM/status work here.
    update_id = update.get("update_id")
    kind = "callback_query" if "callback_query" in update else "message" if "message" in update else "other"
    log.debug("WEBHOOK received update_id=%s kind=%s", update_id, kind)
    threading.Thread(target=process_update_background, args=(update,), daemon=False).start()
    return JSONResponse({"ok": True, "queued": True})
