"""Unit tests for similarity_checker module."""

import pytest
from src.similarity_checker import (
    normalize_for_similarity,
    extract_post_body,
    similarity_ratio,
    similarity_warning,
    clear_normalized_cache,
    get_cache_stats,
    DEFAULT_HISTORY_LIMIT,
)


def test_normalize_for_similarity():
    # Test URL removal
    text = "Check this https://example.com link"
    normalized = normalize_for_similarity(text)
    assert "https" not in normalized
    assert "example.com" not in normalized

    # Test hashtag/cashtag removal
    text = "Bitcoin #BTC $BTC is rising"
    normalized = normalize_for_similarity(text)
    assert "#" not in normalized
    assert "$" not in normalized

    # Test banned phrase removal
    text = "Coin đang vào vùng đáng chú ý vì có đủ 3 yếu tố"
    normalized = normalize_for_similarity(text)
    assert "vùng đáng chú ý" not in normalized
    assert "đủ 3 yếu tố" not in normalized

    # Test lowercase conversion
    text = "BITCOIN Bitcoin bitcoin"
    normalized = normalize_for_similarity(text)
    assert normalized == "bitcoin bitcoin bitcoin"

    # Test special character removal
    text = "Test! @#$% 123"
    normalized = normalize_for_similarity(text)
    assert "!" not in normalized
    assert "%" not in normalized


def test_extract_post_body():
    # Test with metadata
    entry = """Coin: Bitcoin ($BTC)
Status: posted
SquareURL: https://example.com
=== POST THƯỜNG ===
This is the actual post content.
With multiple lines.
#BTC $BTC"""

    body = extract_post_body(entry)
    assert "Coin:" not in body
    assert "Status:" not in body
    assert "SquareURL:" not in body
    assert "This is the actual post content." in body
    assert "With multiple lines." in body

    # Test without metadata
    entry = """=== POST THƯỜNG ===
Just the post content here."""

    body = extract_post_body(entry)
    assert "Just the post content here." in body


def test_similarity_ratio():
    # Test identical texts
    text1 = "Bitcoin is rising today"
    text2 = "Bitcoin is rising today"
    ratio = similarity_ratio(text1, text2)
    assert ratio > 0.9

    # Test completely different texts
    text1 = "Bitcoin is rising"
    text2 = "Ethereum is falling"
    ratio = similarity_ratio(text1, text2)
    assert ratio < 0.5

    # Test similar texts with different coins (should be low due to normalization)
    text1 = "Bitcoin #BTC $BTC đang tăng mạnh với volume cao"
    text2 = "Ethereum #ETH $ETH đang tăng mạnh với volume cao"
    ratio = similarity_ratio(text1, text2)
    # After removing tags, the core content is similar
    assert 0.3 < ratio < 0.9

    # Test empty strings
    assert similarity_ratio("", "") == 0.0
    assert similarity_ratio("test", "") == 0.0


def test_similarity_warning():
    # Test below threshold
    warning = similarity_warning(0.5, threshold=0.98)
    assert "✅" in warning
    assert "50.0%" in warning

    # Test above threshold
    warning = similarity_warning(0.99, threshold=0.98)
    assert "🚫" in warning
    assert "99.0%" in warning
    assert "KHÔNG đăng" in warning

    # Test at threshold
    warning = similarity_warning(0.98, threshold=0.98)
    assert "✅" in warning  # Equal is not greater than


def test_normalize_banned_phrases():
    """Test that all banned phrases are properly removed."""
    banned_phrases = [
        "vùng đáng chú ý",
        "đủ 3 yếu tố",
        "lý do chọn",
        "điểm cần xác nhận",
        "rủi ro chính",
        "theo dõi thêm",
        "phản ứng giá",
        "dòng tiền",
        "anh em đang",
        "chỉ là một pha fomo",
        "hot coin",
        "coin đang nóng",
    ]

    for phrase in banned_phrases:
        text = f"Test {phrase} in sentence"
        normalized = normalize_for_similarity(text)
        # The phrase should be replaced with spaces
        assert phrase not in normalized.lower()


def test_normalize_cache():
    """Test that normalization caching works correctly."""
    # Clear cache first
    clear_normalized_cache()

    text = "Bitcoin #BTC $BTC is rising today"

    # First call should cache
    result1 = normalize_for_similarity(text, use_cache=True)

    # Second call should use cache
    result2 = normalize_for_similarity(text, use_cache=True)

    assert result1 == result2

    # Check cache stats
    stats = get_cache_stats()
    assert stats["cache_size"] >= 1
    assert stats["cache_limit"] == 100


def test_normalize_without_cache():
    """Test that normalization works without caching."""
    text = "Bitcoin #BTC $BTC is rising today"

    result1 = normalize_for_similarity(text, use_cache=False)
    result2 = normalize_for_similarity(text, use_cache=False)

    assert result1 == result2


def test_clear_normalized_cache():
    """Test clearing the normalized cache."""
    # Add some entries
    normalize_for_similarity("test1", use_cache=True)
    normalize_for_similarity("test2", use_cache=True)

    # Clear cache
    count = clear_normalized_cache()
    assert count >= 0

    # Check cache is empty
    stats = get_cache_stats()
    assert stats["cache_size"] == 0


def test_default_history_limit():
    """Test that default history limit is 5."""
    assert DEFAULT_HISTORY_LIMIT == 5
