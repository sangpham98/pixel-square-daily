"""Telegram bot integration for draft delivery and user interaction."""

from __future__ import annotations

import threading
import time

import requests

from .logger import log
from .models import DraftQueueItem
from .utils import env


def telegram_api(method: str, payload: dict, timeout: int = 4) -> dict:
    token = env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN in .env")
    log.debug("TG API start %s", method)
    try:
        response = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=timeout)
        response.raise_for_status()
        log.debug("TG API done %s", method)
        return response.json()
    except Exception as exc:
        log.error("TG API error %s: %s", method, exc)
        raise


def telegram_send_best_effort(chat_id: int | str, text: str, **extra) -> None:
    payload = {"chat_id": chat_id, "text": text, **extra}
    try:
        telegram_api("sendMessage", payload, timeout=4)
    except Exception:
        # Retry once in a detached thread; do not block webhook handling.
        def retry():
            time.sleep(2)
            try:
                telegram_api("sendMessage", payload, timeout=8)
            except Exception as exc:
                log.error("TG API retry failed sendMessage: %s", exc)
        threading.Thread(target=retry, daemon=True).start()


def draft_keyboard() -> dict:
    return {
        "inline_keyboard": [[
            {"text": "📝 Tạo post thường", "callback_data": "pixel_generate_short"},
        ], [
            {"text": "📦 Tạo batch 3 bài", "callback_data": "pixel_generate_batch"},
        ], [
            {"text": "📋 Xem draft queue", "callback_data": "pixel_draft_queue"},
        ], [
            {"text": "📤 Đăng bài tiếp theo", "callback_data": "pixel_post_next"},
        ], [
            {"text": "🔑 Set API key Binance", "callback_data": "pixel_set_api_key"},
        ], [
            {"text": "📊 Status", "callback_data": "pixel_status"},
        ], [
            {"text": "📈 Phân bố góc", "callback_data": "pixel_angles"},
        ]]
    }


def draft_queue_keyboard(queue: list[DraftQueueItem]) -> dict:
    rows = [
        [{"text": f"🗑 Xóa #{idx} {item.coin_symbol}", "callback_data": f"pixel_delete_draft:{idx}"}]
        for idx, item in enumerate(queue, 1)
    ]
    rows.append([{"text": "🔄 Refresh", "callback_data": "pixel_draft_queue"}])
    return {"inline_keyboard": rows}



def send_telegram(message: str, reply_markup: dict | None = None) -> None:
    chat_id = env("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise RuntimeError("Missing TELEGRAM_CHAT_ID in .env")

    # Telegram has 4096 char limit; split safely.
    chunks = [message[i : i + 3800] for i in range(0, len(message), 3800)]
    for idx, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
        if reply_markup and idx == len(chunks) - 1:
            payload["reply_markup"] = reply_markup
        telegram_api("sendMessage", payload)
        time.sleep(0.3)


def answer_callback(callback_query_id: str, text: str = "Đang xử lý...") -> None:
    try:
        telegram_api("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text}, timeout=3)
    except Exception as exc:
        log.error("answerCallbackQuery failed: %s", exc)
