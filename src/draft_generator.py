"""Draft generation pipeline: search, generate, similarity check."""

from __future__ import annotations

import contextlib
import fcntl
import html
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, unquote, urlparse

from ddgs import DDGS

from .coin_selector import CoinContext, select_hot_coin
from .content_generator import (
    build_prompt,
    call_llm,
    enforce_required_terms,
    validate_post,
)
from .history import append_history, recent_history_texts
from .logger import log
from .models import SquarePost
from .similarity_checker import DEFAULT_HISTORY_LIMIT, max_history_similarity, similarity_warning
from .utils import env

LOCK_FILE = Path(__file__).parent.parent / "pixel_generation.lock"
SIMILARITY_MAX_REGENERATIONS = int(os.getenv("SIMILARITY_MAX_REGENERATIONS", "3"))
SIMILARITY_BLOCK_THRESHOLD = float(os.getenv("SIMILARITY_BLOCK_THRESHOLD", "0.98"))


# --- Search ---


def search_duckduckgo(query: str, max_results: int = 5) -> list[SquarePost]:
    """Search DuckDuckGo via ddgs for crypto content; no URL filter."""
    posts: list[SquarePost] = []
    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=max_results)
            for item in results:
                url = item.get("href") or item.get("url") or ""
                title = (item.get("title") or item.get("header") or "").strip()
                snippet = (item.get("description") or item.get("body") or "").strip()
                if title and url:
                    posts.append(SquarePost(title=title, url=url, snippet=snippet))
        return dedupe_posts(posts)
    except Exception as exc:
        log.warning("DDGS failed for %r: %s", query, exc)
        return []


def normalize_result_url(raw_url: str) -> str:
    raw_url = html.unescape(raw_url)
    if "uddg=" in raw_url:
        parsed = urlparse(raw_url)
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return raw_url


def is_square_post_url(url: str) -> bool:
    return "binance.com" in url and "/square/post/" in url


def dedupe_posts(posts: Iterable[SquarePost]) -> list[SquarePost]:
    seen: set[str] = set()
    unique: list[SquarePost] = []
    for post in posts:
        key = post.url.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        unique.append(post)
    return unique


def fetch_coin_posts(coin: CoinContext) -> list[SquarePost]:
    symbol = coin.symbol.upper()
    name = coin.name
    queries = [
        f"{symbol} {name} binance square crypto price analysis",
        f"${symbol} {name} crypto market trending analysis",
        f"{name} {symbol} binance square latest news",
        f"{symbol} {name} crypto breakout volume support resistance",
        f"{symbol} {name} crypto catalyst news fundamental",
        f"{symbol} {name} crypto defi layer2 ai",
    ]

    posts: list[SquarePost] = []
    for query in queries:
        try:
            posts.extend(search_duckduckgo(query, max_results=5))
        except Exception as exc:
            log.warning("Search failed for %r: %s", query, exc)
    return dedupe_posts(posts)[:20]


# --- History ---


def save_history(draft: str, coin: CoinContext | None = None, angle: str = "", square_url: str = "", status: str = "") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    append_history(
        timestamp=timestamp,
        coin_name=coin.name if coin else "",
        coin_symbol=coin.symbol if coin else "",
        content=draft,
        status=status,
        angle=angle,
        square_url=square_url,
    )


# --- Locking ---


@contextlib.contextmanager
def generation_lock(blocking: bool = False):
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = open(LOCK_FILE, "w")
    try:
        if blocking:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        else:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()


# --- Draft generation ---


def build_draft(mode: str = "both", excluded_symbols: Iterable[str] | None = None) -> tuple[str, list[SquarePost], bool, CoinContext, str]:
    coin = select_hot_coin(excluded_symbols=excluded_symbols)
    posts = fetch_coin_posts(coin)
    from_cache = False
    prompt, angle_name = build_prompt(posts, coin, mode=mode)
    draft = call_llm(prompt, fallback_coin=coin)
    draft = enforce_required_terms(draft, coin.required_tags)
    return draft, posts, from_cache, coin, angle_name


def build_draft_with_similarity(
    mode: str = "both",
    max_regenerations: int | None = None,
    excluded_symbols: Iterable[str] | None = None,
) -> tuple[str, list[SquarePost], bool, float, int, CoinContext, str]:
    if max_regenerations is None:
        max_regenerations = SIMILARITY_MAX_REGENERATIONS
    last_draft = ""
    last_posts: list[SquarePost] = []
    last_from_cache = False
    last_score = 0.0
    last_attempt = 0
    last_coin = CoinContext(name="Bitcoin", symbol="BTC", reason="fallback")
    last_angle = ""

    history_texts = recent_history_texts(limit=DEFAULT_HISTORY_LIMIT)

    for attempt in range(max_regenerations + 1):
        draft, posts, from_cache, coin, angle_name = build_draft(mode=mode, excluded_symbols=excluded_symbols)
        score, _ = max_history_similarity(draft, history_texts=history_texts)
        last_draft, last_posts, last_from_cache, last_score, last_attempt, last_coin, last_angle = draft, posts, from_cache, score, attempt, coin, angle_name
        log.info("Similarity check attempt %d: %.3f", attempt + 1, score)
        if score <= SIMILARITY_BLOCK_THRESHOLD:
            return draft, posts, from_cache, score, attempt, coin, angle_name
    log.warning("Max regenerations reached. Best similarity: %.3f", last_score)
    return last_draft, last_posts, last_from_cache, last_score, last_attempt, last_coin, last_angle
