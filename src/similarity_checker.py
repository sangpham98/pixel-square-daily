"""Similarity checking functions to prevent duplicate content."""

from __future__ import annotations

import difflib
import re


DEFAULT_HISTORY_LIMIT = 5  # Reduced from 8 to 5 for better performance

# Cache for normalized text to avoid re-processing
_normalized_cache: dict[str, str] = {}


def extract_post_body(entry: str) -> str:
    """Strip metadata and post header so similarity only compares actual post content."""
    lines = entry.split("\n")
    body_lines = []
    in_post_content = False
    for line in lines:
        if line.startswith((
            "Coin:", "Status:", "SquareURL:", "Coin chọn", "Nguồn:", "Similarity:",
            "Auto-post:", "Angle:", "Sources:", "---", "Regenerate",
        )):
            continue
        if line.startswith(("===",)):
            in_post_content = True
            continue
        if in_post_content:
            body_lines.append(line)
    return "\n".join(body_lines).strip()


def normalize_for_similarity(text: str, use_cache: bool = True) -> str:
    """Strip template phrases to prevent false-positive similarity across different coins.

    Args:
        text: Text to normalize
        use_cache: Whether to use cached normalized text (default True)
    """
    # Check cache first
    if use_cache and text in _normalized_cache:
        return _normalized_cache[text]

    normalized = text.lower()
    normalized = re.sub(r"https?://\S+", " ", normalized)
    normalized = re.sub(r"[@#$][\w]+", " ", normalized)
    # Remove common crypto content template phrases that appear in every post.
    normalized = re.sub(
        r"\b(vùng đáng chú ý|vùng nào|đang vào vùng|đang đáng chú ý"
        r"|đủ 3 yếu tố|đủ yếu tố"
        r"|lý do chọn|reason|coin chọn hôm nay"
        r"|điểm cần xác nhận|cần xác nhận"
        r"|rủi ro chính|rủi ro"
        r"|theo dõi thêm|theo dõi"
        r"|phản ứng giá|phản ứng"
        r"|dòng tiền|dòng"
        r"|trước khi quyết định|quyết định"
        r"|anh em đang|anh em"
        r"|quality score|not used in last"
        r"|chỉ là một pha fomo|fomo|fear of missing out"
        r"|thị trường chung|thị trường đảo chiều"
        r"|hot coin|coin nóng"
        r"|coingecko trending|trending search|market data|market mover"
        r"|độ nhận diện|thanh khoản|biến động"
        r"|coin đang nóng|nóng thường|điều chỉnh nhanh"
        r"|volume có giữ|giữ được nhịp"
        r")\b",
        " ",
        normalized,
    )
    normalized = re.sub(r"[^a-z0-9à-ỹ\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Cache the result (limit cache size to prevent memory issues)
    if use_cache and len(_normalized_cache) < 100:
        _normalized_cache[text] = normalized

    return normalized


def similarity_ratio(a: str, b: str) -> float:
    a_norm = normalize_for_similarity(a)
    b_norm = normalize_for_similarity(b)
    if not a_norm or not b_norm:
        return 0.0
    return difflib.SequenceMatcher(None, a_norm, b_norm).ratio()


def max_history_similarity(content: str, history_texts: list[str] | None = None) -> tuple[float, int]:
    """Compare content against history entries, stripping coin metadata first.

    Only the actual post body (hook + bullets + CTA) is compared, not the coin name,
    symbol, hashtags, or metadata. This prevents true different-coin posts from
    being blocked just because they use the same LLM template structure.

    Args:
        content: Content to check for similarity
        history_texts: List of raw history entry texts to compare against.
            If None, returns (0.0, -1) — caller must provide history.

    Returns:
        Tuple of (best_similarity_ratio, best_match_index)
    """
    if not history_texts:
        return 0.0, -1

    best_ratio = 0.0
    best_index = -1
    post_body = extract_post_body(content)
    post_body_normalized = normalize_for_similarity(post_body)

    for idx, entry in enumerate(history_texts, 1):
        entry_body = extract_post_body(entry)
        entry_body_normalized = normalize_for_similarity(entry_body)

        if not post_body_normalized or not entry_body_normalized:
            continue

        ratio = difflib.SequenceMatcher(None, post_body_normalized, entry_body_normalized).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_index = idx

    return best_ratio, best_index


def similarity_warning(score: float, threshold: float = 0.98) -> str:
    percent = round(score * 100, 1)
    threshold_percent = round(threshold * 100, 1)
    if score > threshold:
        return f"🚫 Similarity: {percent}% - vượt ngưỡng {threshold_percent}%, KHÔNG đăng Binance Square. Hãy bấm tạo lại."
    return f"✅ Similarity: {percent}% - dưới ngưỡng {threshold_percent}%, đủ điều kiện đăng."


def clear_normalized_cache() -> int:
    """Clear the normalized text cache and return number of entries cleared."""
    count = len(_normalized_cache)
    _normalized_cache.clear()
    return count


def get_cache_stats() -> dict[str, int]:
    """Get statistics about the normalized text cache."""
    return {
        "cache_size": len(_normalized_cache),
        "cache_limit": 100,
    }
