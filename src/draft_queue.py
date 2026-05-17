"""Draft queue persistence and batch generation."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .coin_selector import CoinContext
from .content_generator import extract_short_post, validate_post
from .logger import log
from .models import DraftQueueItem

DRAFT_QUEUE_FILE = Path(__file__).parent.parent / "draft_queue.json"


def load_draft_queue() -> list[DraftQueueItem]:
    if not DRAFT_QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(DRAFT_QUEUE_FILE.read_text(encoding="utf-8"))
        return [DraftQueueItem(**item) for item in data]
    except Exception as exc:
        log.warning("Failed to load draft queue: %s", exc)
        return []


def save_draft_queue(queue: list[DraftQueueItem]) -> None:
    DRAFT_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(item) for item in queue]
    DRAFT_QUEUE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_draft_batch(count: int = 3) -> list[DraftQueueItem]:
    """Generate multiple drafts and save to queue."""
    from .draft_generator import build_draft_with_similarity

    queue: list[DraftQueueItem] = []
    for i in range(count):
        try:
            draft, posts, from_cache, similarity_score, attempt, coin, angle_name = build_draft_with_similarity(mode="short")
            short_post = extract_short_post(draft)
            item = DraftQueueItem(
                coin_symbol=coin.symbol.upper(),
                coin_name=coin.name,
                coin_reason=coin.reason,
                draft=draft,
                short_post=short_post,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                angle=angle_name,
            )
            queue.append(item)
            log.info("Batch %d/%d: generated draft for %s (%s), angle=%s", i + 1, count, coin.name, coin.cashtag, angle_name)
        except Exception as exc:
            log.error("Batch generation failed at %d/%d: %s", i + 1, count, exc)
            break
    save_draft_queue(queue)
    return queue


def post_next_from_queue() -> tuple[DraftQueueItem | None, str | None]:
    """Post the next draft from queue. Returns (item, url) or (None, error)."""
    from .binance_api import post_to_binance_square
    from .draft_generator import save_history

    queue = load_draft_queue()
    if not queue:
        return None, "Queue trống"
    item = queue[0]
    try:
        square_url = post_to_binance_square(item.short_post)
        save_history(
            f"Status: {'posted' if square_url else 'draft_only'}\n"
            f"Coin: {item.coin_name} (${item.coin_symbol})\n"
            f"Angle: {item.angle}\n"
            f"SquareURL: {square_url or 'N/A'}\n"
            f"{item.draft}"
        )
        queue.pop(0)
        save_draft_queue(queue)
        log.info("Posted queued draft for %s, %d remaining", item.coin_symbol, len(queue))
        return item, square_url
    except Exception as exc:
        log.error("Failed to post queued draft: %s", exc)
        return None, str(exc)
