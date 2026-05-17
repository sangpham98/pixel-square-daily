#!/usr/bin/env python3
"""Daily hot-coin Binance Square content drafter.

Entry point for scheduled runs and CLI testing.
Telegram handlers and draft logic live in src/ modules.

Usage:
  RUN_ONCE=true python pixel_square_daily.py   # one-shot test
  python pixel_square_daily.py                  # schedule + bot listener
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime

import schedule
from dotenv import load_dotenv

from src import (
    build_prompt,
    draft_keyboard,
    extract_short_post,
    post_to_binance_square,
    send_telegram,
    similarity_warning,
    validate_post,
)
from src.draft_generator import (
    SIMILARITY_BLOCK_THRESHOLD,
    build_draft_with_similarity,
    generation_lock,
    save_history,
)
from src.history import init_db, migrate_from_txt
from src.logger import log
from src.telegram_handlers import run_bot_listener
from src.utils import env

load_dotenv()

# Initialize SQLite database and migrate legacy data
init_db()
migrate_from_txt()


def run_job() -> None:
    log.info("Running hot-coin daily draft job")
    try:
        with generation_lock(blocking=False):
            draft, posts, from_cache, similarity_score, similarity_attempt, coin, angle_name = build_draft_with_similarity(mode="short")
            short_post = extract_short_post(draft)
            validation_issues = validate_post(short_post, coin)
            if validation_issues:
                log.warning("Post validation issues: %s", "; ".join(validation_issues))
            blocked_by_similarity = similarity_score > SIMILARITY_BLOCK_THRESHOLD
            square_url = None if blocked_by_similarity else post_to_binance_square(short_post)
            post_status = "🚫 Không đăng: similarity vượt ngưỡng, cần tạo lại" if blocked_by_similarity else (square_url or "OFF / chưa đăng")

            validation_line = ""
            if validation_issues:
                validation_line = f"\n⚠️ Validation: {'; '.join(validation_issues)}"

            message = (
                f"🧾 Hot coin Binance Square daily draft - {datetime.now():%Y-%m-%d %H:%M}\n"
                f"Coin hôm nay: {coin.name} ({coin.cashtag})\n"
                f"Angle: {angle_name}\n"
                f"Lý do chọn: {coin.reason}\n"
                f"Đã tham khảo {len(posts)} nguồn{' cache' if from_cache else ''}. Review trước khi đăng.\n\n"
                f"{draft}\n\n"
                f"{similarity_warning(similarity_score, SIMILARITY_BLOCK_THRESHOLD)}\n"
                f"Regenerate attempts: {similarity_attempt}\n"
                f"Binance Square auto-post: {post_status}"
                f"{validation_line}"
            )
            send_telegram(message, reply_markup=draft_keyboard())
            if blocked_by_similarity:
                log.info("Draft sent to Telegram but not saved to history because similarity was blocked")
            else:
                save_history(draft, coin=coin, angle=angle_name, square_url=square_url or "", status="posted" if square_url else "draft_only")
                log.info("Draft sent to Telegram and saved to history")
    except BlockingIOError:
        log.warning("Another generation is already running; skipping this run")
    except Exception as exc:
        log.exception("Job failed: %s", exc)


def main() -> None:
    if env("RUN_ONCE", "false").lower() in {"1", "true", "yes"}:
        run_job()
        return

    schedule_time = env("SCHEDULE_TIME", "09:00")
    schedule.every().day.at(schedule_time).do(run_job)
    log.info("Scheduled daily job at %s", schedule_time)

    bot_thread = threading.Thread(target=run_bot_listener, daemon=True)
    bot_thread.start()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
