"""Telegram interaction: handlers, workers, polling, status."""

from __future__ import annotations

import fcntl
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from .binance_api import post_to_binance_square, set_user_square_key
from .coin_selector import CoinContext
from .content_generator import extract_short_post, validate_post
from .draft_generator import (
    LOCK_FILE,
    SIMILARITY_BLOCK_THRESHOLD,
    build_draft_with_similarity,
    generation_lock,
    save_history,
    similarity_warning,
)
from .draft_queue import (
    generate_draft_batch,
    load_draft_queue,
    post_next_from_queue,
)
from .history import angle_distribution, latest_history_time as _latest_history_time
from .logger import log
from .telegram_bot import (
    answer_callback,
    draft_keyboard,
    send_telegram,
    telegram_api,
    telegram_send_best_effort,
)
from .utils import env

OFFSET_FILE = Path(__file__).parent.parent / "telegram_offset.txt"
USER_KEY_PENDING: set[str] = set()


# --- Status ---


def systemctl_user_status(unit: str, prop: str = "ActiveState") -> str:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show", unit, f"--property={prop}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            line = result.stdout.strip()
            if "=" in line:
                return line.split("=", 1)[1]
    except Exception:
        pass
    return "unknown"


def latest_history_time() -> str:
    return _latest_history_time() or "N/A"


def lock_status() -> str:
    if not LOCK_FILE.exists():
        return "🟢 Không có generation đang chạy"
    try:
        with open(LOCK_FILE, "r") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return "🟢 Lock file tồn tại nhưng không bị lock"
    except BlockingIOError:
        return "🔴 Generation đang chạy (lock active)"
    except Exception as exc:
        return f"⚠️  Không kiểm tra được lock: {exc}"


def build_status_message() -> str:
    service_state = systemctl_user_status("pixel-square-daily.service")
    timer_state = systemctl_user_status("pixel-square-daily.timer")
    last_post = latest_history_time()
    lock_info = lock_status()
    return (
        f"📊 Pixel Square Daily Status\n\n"
        f"Service: {service_state}\n"
        f"Timer: {timer_state}\n"
        f"Last post: {last_post}\n"
        f"{lock_info}"
    )


def send_status(chat_id: int | str) -> None:
    telegram_send_best_effort(chat_id, build_status_message())


def run_status_async(chat_id: int | str) -> None:
    threading.Thread(target=lambda: send_status(chat_id), daemon=True).start()


# --- Async workers ---


def run_generation_async(chat_id: int | str, mode: str) -> None:
    def worker():
        try:
            with generation_lock(blocking=False):
                draft, posts, from_cache, similarity_score, similarity_attempt, coin, angle_name = build_draft_with_similarity(mode=mode)
                short_post = extract_short_post(draft)
                validation_issues = validate_post(short_post, coin)
                if validation_issues:
                    log.warning("Post validation issues: %s", "; ".join(validation_issues))
                blocked_by_similarity = similarity_score > SIMILARITY_BLOCK_THRESHOLD
                square_url = None if blocked_by_similarity else post_to_binance_square(short_post, user_id=chat_id)
                post_status = "🚫 Không đăng: similarity vượt ngưỡng" if blocked_by_similarity else (square_url or "OFF / chưa đăng")

                validation_line = ""
                if validation_issues:
                    validation_line = f"\n⚠️ Validation: {'; '.join(validation_issues)}"

                message = (
                    f"✅ Generation hoàn tất\n"
                    f"Coin: {coin.name} ({coin.cashtag})\n"
                    f"Angle: {angle_name}\n"
                    f"Lý do: {coin.reason}\n"
                    f"Nguồn: {len(posts)}{' cache' if from_cache else ''}\n\n"
                    f"{draft}\n\n"
                    f"{similarity_warning(similarity_score, SIMILARITY_BLOCK_THRESHOLD)}\n"
                    f"Regenerate: {similarity_attempt}\n"
                    f"Auto-post: {post_status}"
                    f"{validation_line}"
                )
                telegram_send_best_effort(chat_id, message)
                if not blocked_by_similarity:
                    save_history(draft, coin=coin, angle=angle_name, square_url=square_url or "", status="posted" if square_url else "draft_only")
        except BlockingIOError:
            telegram_send_best_effort(chat_id, "⚠️ Generation đang chạy, vui lòng đợi")
        except Exception as exc:
            telegram_send_best_effort(chat_id, f"❌ Generation thất bại: {exc}")
    threading.Thread(target=worker, daemon=True).start()


def run_batch_generation_async(chat_id: int | str) -> None:
    def worker():
        try:
            with generation_lock(blocking=False):
                telegram_send_best_effort(chat_id, "📦 Đang tạo batch 3 bài, vui lòng đợi...")
                queue = generate_draft_batch(count=3)
                if not queue:
                    telegram_send_best_effort(chat_id, "❌ Không tạo được bài nào")
                    return
                lines = [f"📦 Đã tạo {len(queue)} bài draft:"]
                for i, item in enumerate(queue, 1):
                    validation = validate_post(item.short_post, CoinContext(name=item.coin_name, symbol=item.coin_symbol, reason=item.coin_reason))
                    status = "⚠️ " + "; ".join(validation) if validation else "✅"
                    lines.append(f"{i}. {item.coin_name} (${item.coin_symbol}) {status}")
                lines.append(f"\nBấm 📤 Đăng bài tiếp theo để đăng dần.")
                telegram_send_best_effort(chat_id, "\n".join(lines))
        except BlockingIOError:
            telegram_send_best_effort(chat_id, "⚠️ Generation đang chạy, vui lòng đợi")
        except Exception as exc:
            telegram_send_best_effort(chat_id, f"❌ Batch generation thất bại: {exc}")
    threading.Thread(target=worker, daemon=True).start()


def run_post_next_async(chat_id: int | str) -> None:
    def worker():
        try:
            item, result = post_next_from_queue()
            if item is None:
                telegram_send_best_effort(chat_id, f"ℹ️ {result}")
                return
            queue = load_draft_queue()
            remaining = len(queue)
            square_status = result or "OFF / chưa đăng"
            message = (
                f"✅ Đã đăng bài cho {item.coin_name} (${item.coin_symbol})\n"
                f"URL: {square_status}\n"
                f"Còn {remaining} bài trong queue"
            )
            telegram_send_best_effort(chat_id, message)
        except Exception as exc:
            telegram_send_best_effort(chat_id, f"❌ Post next thất bại: {exc}")
    threading.Thread(target=worker, daemon=True).start()


# --- Analytics ---


def build_angles_message() -> str:
    """Parse history and show angle distribution."""
    dist = angle_distribution()
    if not dist:
        return "📊 Chưa có bài nào có Angle trong history."
    total = sum(dist.values())
    lines = [f"📊 Angle distribution ({total} bài):"]
    for angle, count in sorted(dist.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        bar = "█" * int(pct / 5)
        lines.append(f"  {angle}: {count} ({pct:.0f}%) {bar}")
    return "\n".join(lines)


# --- Update dispatch ---


def handle_update(update: dict) -> None:
    message = update.get("message")
    callback_query = update.get("callback_query")

    if callback_query:
        callback_id = callback_query["id"]
        data = callback_query.get("data", "")
        from_user = callback_query.get("from", {})
        user_id = from_user.get("id")
        chat_id = callback_query.get("message", {}).get("chat", {}).get("id")

        if data == "pixel_generate_short":
            answer_callback(callback_id, "Đang tạo post...")
            run_generation_async(chat_id, mode="short")
        elif data == "pixel_generate_batch":
            answer_callback(callback_id, "Đang tạo batch 3 bài...")
            run_batch_generation_async(chat_id)
        elif data == "pixel_post_next":
            answer_callback(callback_id, "Đang đăng bài tiếp theo...")
            run_post_next_async(chat_id)
        elif data == "pixel_status":
            answer_callback(callback_id, "Đang lấy status...")
            run_status_async(chat_id)
        elif data == "pixel_set_api_key":
            answer_callback(callback_id, "Gửi API key qua tin nhắn riêng")
            USER_KEY_PENDING.add(str(user_id))
            telegram_send_best_effort(chat_id, "Vui lòng gửi Binance Square OpenAPI key của bạn (tin nhắn tiếp theo):")
        elif data == "pixel_angles":
            answer_callback(callback_id, "Đang lấy stats...")
            telegram_send_best_effort(chat_id, build_angles_message())
        else:
            answer_callback(callback_id, "Unknown action")
        return

    if message:
        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")
        text = (message.get("text") or "").strip()

        if str(user_id) in USER_KEY_PENDING:
            USER_KEY_PENDING.discard(str(user_id))
            try:
                masked = set_user_square_key(user_id, text)
                telegram_send_best_effort(chat_id, f"✅ API key đã lưu: {masked}")
            except ValueError as exc:
                telegram_send_best_effort(chat_id, f"❌ {exc}")
            return

        if text.startswith("/"):
            cmd = text.split()[0].lower()
            if cmd == "/start":
                telegram_send_best_effort(chat_id, "👋 Pixel Square Daily Bot\nGõ /menu để mở menu.")
            elif cmd == "/status":
                run_status_async(chat_id)
            elif cmd == "/generate":
                run_generation_async(chat_id, mode="short")
            elif cmd == "/angles":
                telegram_send_best_effort(chat_id, build_angles_message())
            elif cmd == "/menu":
                telegram_send_best_effort(chat_id, "📋 Menu:", reply_markup=draft_keyboard())
            else:
                telegram_send_best_effort(chat_id, "Unknown command")


# --- Polling ---


def load_update_offset() -> int | None:
    if not OFFSET_FILE.exists():
        return None
    try:
        return int(OFFSET_FILE.read_text().strip())
    except Exception:
        return None


def save_update_offset(offset: int) -> None:
    OFFSET_FILE.write_text(str(offset))


def telegram_get_updates(offset: int | None) -> dict:
    payload = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
    if offset is not None:
        payload["offset"] = offset
    return telegram_api("getUpdates", payload, timeout=35)


def get_latest_update_offset() -> int | None:
    try:
        data = telegram_get_updates(None)
        if not data.get("ok"):
            return None
        updates = data.get("result", [])
        if not updates:
            return None
        return max(u["update_id"] for u in updates) + 1
    except Exception as exc:
        log.error("Failed to get latest offset: %s", exc)
        return None


def run_bot_listener() -> None:
    offset = load_update_offset()
    if offset is None:
        offset = get_latest_update_offset()
        if offset is not None:
            save_update_offset(offset)
            log.info("Initialized offset to %d", offset)

    log.info("Telegram bot listener started")
    while True:
        try:
            data = telegram_get_updates(offset)
            if not data.get("ok"):
                log.warning("getUpdates not ok: %s", data)
                time.sleep(5)
                continue

            updates = data.get("result", [])
            for update in updates:
                update_id = update["update_id"]
                offset = update_id + 1
                save_update_offset(offset)
                try:
                    handle_update(update)
                except Exception as exc:
                    log.exception("Failed to handle update %s: %s", update_id, exc)
        except Exception as exc:
            log.error("Bot listener error: %s", exc)
            time.sleep(5)
