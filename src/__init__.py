"""Pixel Square Daily - Modular crypto content generator for Binance Square."""

from .binance_api import (
    get_user_square_key,
    has_user_square_key,
    load_user_keys,
    post_to_binance_square,
    save_user_keys,
    set_user_square_key,
)
from .history import (
    HistoryEntry,
    append_history,
    angle_distribution,
    init_db,
    latest_history_time,
    load_history_entries,
    migrate_from_txt,
    recent_coin_symbols,
    recent_history_texts,
    total_posts,
)
from .cache import APICache
from .coin_selector import (
    CoinContext,
    coin_from_market_row,
    enrich_trending_with_market_data,
    score_coin,
    select_hot_coin,
)
from .content_generator import (
    BANNED_PHRASES,
    CONTENT_ANGLES,
    append_missing_tags,
    build_prompt,
    call_llm,
    call_llm_provider,
    enforce_required_terms,
    extract_article,
    extract_short_post,
    fallback_draft,
    llm_providers,
    load_recent_history,
    select_content_angle,
    split_draft_sections,
    validate_post,
)
from .similarity_checker import (
    extract_post_body,
    max_history_similarity,
    normalize_for_similarity,
    similarity_ratio,
    similarity_warning,
)
from .telegram_bot import (
    answer_callback,
    draft_keyboard,
    send_telegram,
    telegram_api,
    telegram_send_best_effort,
)
from .utils import (
    clean_html,
    compact_usd,
    env,
    mask_key,
    to_float,
)
from .logger import log
from .models import DraftQueueItem, SquarePost
from .draft_queue import (
    delete_draft_by_index,
    generate_draft_batch,
    load_draft_queue,
    post_next_from_queue,
    save_draft_queue,
)
from .draft_generator import (
    build_draft,
    build_draft_with_similarity,
    fetch_coin_posts,
    generation_lock,
    save_history,
    search_duckduckgo,
    SIMILARITY_BLOCK_THRESHOLD,
    SIMILARITY_MAX_REGENERATIONS,
)
from .telegram_handlers import (
    build_angles_message,
    build_status_message,
    handle_update,
    run_bot_listener,
    run_generation_async,
    run_batch_generation_async,
    run_post_next_async,
    run_status_async,
)

__all__ = [
    # binance_api
    "get_user_square_key",
    "has_user_square_key",
    "load_user_keys",
    "post_to_binance_square",
    "save_user_keys",
    "set_user_square_key",
    # cache
    "APICache",
    # coin_selector
    "CoinContext",
    "coin_from_market_row",
    "enrich_trending_with_market_data",
    "score_coin",
    "select_hot_coin",
    # content_generator
    "BANNED_PHRASES",
    "CONTENT_ANGLES",
    "append_missing_tags",
    "build_prompt",
    "call_llm",
    "call_llm_provider",
    "enforce_required_terms",
    "extract_article",
    "extract_short_post",
    "fallback_draft",
    "llm_providers",
    "load_recent_history",
    "select_content_angle",
    "split_draft_sections",
    "validate_post",
    # history
    "HistoryEntry",
    "append_history",
    "angle_distribution",
    "init_db",
    "latest_history_time",
    "load_history_entries",
    "migrate_from_txt",
    "recent_coin_symbols",
    "recent_history_texts",
    "total_posts",
    # similarity_checker
    "extract_post_body",
    "max_history_similarity",
    "normalize_for_similarity",
    "similarity_ratio",
    "similarity_warning",
    # logger
    "log",
    # telegram_bot
    "answer_callback",
    "draft_keyboard",
    "send_telegram",
    "telegram_api",
    "telegram_send_best_effort",
    # utils
    "clean_html",
    "compact_usd",
    "env",
    "mask_key",
    "to_float",
    # models
    "DraftQueueItem",
    "SquarePost",
    # draft_queue
    "delete_draft_by_index",
    "generate_draft_batch",
    "load_draft_queue",
    "post_next_from_queue",
    "save_draft_queue",
    # draft_generator
    "build_draft",
    "build_draft_with_similarity",
    "fetch_coin_posts",
    "generation_lock",
    "save_history",
    "search_duckduckgo",
    "SIMILARITY_BLOCK_THRESHOLD",
    "SIMILARITY_MAX_REGENERATIONS",
    # telegram_handlers
    "build_angles_message",
    "build_status_message",
    "handle_update",
    "run_bot_listener",
    "run_generation_async",
    "run_batch_generation_async",
    "run_post_next_async",
    "run_status_async",
]
