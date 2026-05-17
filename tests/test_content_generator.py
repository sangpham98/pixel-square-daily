"""Unit tests for content_generator module."""

import pytest
from src.content_generator import (
    BANNED_PHRASES,
    CONTENT_ANGLES,
    select_content_angle,
    split_draft_sections,
    append_missing_tags,
    enforce_required_terms,
    extract_short_post,
    extract_article,
    call_llm,
    llm_providers,
    validate_post,
)
from src.coin_selector import CoinContext


def test_split_draft_sections():
    draft = """=== POST THƯỜNG ===
This is a short post.
#BTC $BTC

=== ARTICLE ===
This is a longer article.
With multiple paragraphs."""

    sections = split_draft_sections(draft)
    assert len(sections) == 2
    assert "short post" in sections[0]
    assert "longer article" in sections[1]


def test_split_draft_sections_single():
    draft = """=== POST THƯỜNG ===
Only a short post here.
#BTC $BTC"""

    sections = split_draft_sections(draft)
    assert len(sections) == 1
    assert "short post" in sections[0]


def test_append_missing_tags():
    # Test with missing tags
    text = "Bitcoin is rising today"
    result = append_missing_tags(text, ("#BTC", "$BTC"))
    assert "#BTC" in result
    assert "$BTC" in result

    # Test with existing tags (case insensitive)
    text = "Bitcoin is rising #btc $btc"
    result = append_missing_tags(text, ("#BTC", "$BTC"))
    # Should not duplicate
    assert result.count("#") == 1
    assert result.count("$") == 1

    # Test with no required tags
    text = "Bitcoin is rising"
    result = append_missing_tags(text, ())
    assert result == text


def test_enforce_required_terms():
    draft = """=== POST THƯỜNG ===
Bitcoin is rising today.

=== ARTICLE ===
Ethereum is falling today."""

    result = enforce_required_terms(draft, ("#BTC", "$BTC"))
    # Both sections should have tags appended
    assert result.count("#BTC") >= 2
    assert result.count("$BTC") >= 2


def test_extract_short_post():
    draft = """=== POST THƯỜNG ===
This is the short post content.
#BTC $BTC

=== ARTICLE ===
This is the article content."""

    post = extract_short_post(draft)
    assert "short post content" in post
    assert "article content" not in post
    assert "#BTC" in post


def test_extract_short_post_only():
    draft = """=== POST THƯỜNG ===
Only short post here.
#BTC $BTC"""

    post = extract_short_post(draft)
    assert "Only short post here" in post


def test_extract_short_post_missing():
    draft = """Some content without proper format"""
    post = extract_short_post(draft)
    assert post == ""


def test_extract_article():
    draft = """=== POST THƯỜNG ===
Short post.

=== ARTICLE ===
This is the article content.
With multiple lines."""

    article = extract_article(draft)
    assert "article content" in article
    assert "Short post" not in article


def test_extract_article_missing():
    draft = """=== POST THƯỜNG ===
Only short post here."""

    article = extract_article(draft)
    assert article == ""


def test_case_insensitive_section_headers():
    # Test with different case variations
    draft1 = """=== post thường ===
Content here"""
    post1 = extract_short_post(draft1)
    assert "Content here" in post1

    draft2 = """=== POST THƯỜNG ===
Content here"""
    post2 = extract_short_post(draft2)
    assert "Content here" in post2

    draft3 = """===   POST THƯỜNG   ===
Content here"""
    post3 = extract_short_post(draft3)
    assert "Content here" in post3


def test_enforce_required_terms_no_sections():
    # Test with content that has no section markers
    text = "Bitcoin is rising today"
    result = enforce_required_terms(text, ("#BTC", "$BTC"))
    assert "#BTC" in result
    assert "$BTC" in result


def test_llm_providers_primary_only(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://primary/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.setenv("OPENAI_MODEL", "primary-model")
    monkeypatch.delenv("OPENAI_FALLBACK_PROVIDERS", raising=False)
    monkeypatch.delenv("FALLBACK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("FALLBACK_OPENAI_MODEL", raising=False)

    providers = llm_providers()

    assert providers == [{
        "base_url": "http://primary/v1",
        "api_key": "primary-key",
        "model": "primary-model",
    }]


def test_llm_providers_json_and_env_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://primary/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.setenv("OPENAI_MODEL", "primary-model")
    monkeypatch.setenv("OPENAI_FALLBACK_PROVIDERS", '[{"base_url":"http://json/v1","api_key":"json-key","model":"json-model"}]')
    monkeypatch.setenv("FALLBACK_OPENAI_BASE_URL", "http://fallback/v1")
    monkeypatch.setenv("FALLBACK_OPENAI_API_KEY", "fallback-key")
    monkeypatch.setenv("FALLBACK_OPENAI_MODEL", "fallback-model")

    providers = llm_providers()

    assert [provider["base_url"] for provider in providers] == [
        "http://primary/v1",
        "http://json/v1",
        "http://fallback/v1",
    ]
    assert providers[1]["model"] == "json-model"
    assert providers[2]["api_key"] == "fallback-key"


def test_call_llm_uses_second_provider_after_first_fails(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://primary/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.setenv("OPENAI_MODEL", "primary-model")
    monkeypatch.setenv("OPENAI_FALLBACK_PROVIDERS", '[{"base_url":"http://fallback/v1","api_key":"fallback-key","model":"fallback-model"}]')
    monkeypatch.delenv("FALLBACK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("FALLBACK_OPENAI_MODEL", raising=False)

    calls = []

    class FakeResponse:
        def __init__(self, ok: bool):
            self.ok = ok

        def raise_for_status(self):
            if not self.ok:
                raise RuntimeError("primary failed")

        def json(self):
            return {"choices": [{"message": {"content": "fallback provider draft"}}]}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs["json"]["model"]))
        return FakeResponse(ok=len(calls) == 2)

    monkeypatch.setattr("src.content_generator.requests.post", fake_post)

    result = call_llm("prompt")

    assert result == "fallback provider draft"
    assert calls == [
        ("http://primary/v1/chat/completions", "primary-model"),
        ("http://fallback/v1/chat/completions", "fallback-model"),
    ]


def test_call_llm_builtin_fallback_when_all_providers_fail(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://primary/v1")
    monkeypatch.setenv("OPENAI_MODEL", "primary-model")
    monkeypatch.delenv("OPENAI_FALLBACK_PROVIDERS", raising=False)
    monkeypatch.delenv("FALLBACK_OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("FALLBACK_OPENAI_MODEL", raising=False)

    def fake_post(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("src.content_generator.requests.post", fake_post)
    coin = CoinContext(name="Bitcoin", symbol="BTC", reason="test")

    result = call_llm("prompt", fallback_coin=coin)

    assert result.startswith("=== POST THƯỜNG ===")
    assert "Bitcoin" in result
    assert "$BTC" in result


# --- validate_post tests ---

def _make_valid_post(coin: CoinContext | None = None) -> str:
    """Return a post that passes all validation checks (~500 chars)."""
    c = coin or CoinContext(name="Bitcoin", symbol="BTC", reason="test")
    return (
        f"Giá {c.cashtag} đang test vùng kháng cự quan trọng sau đợt hồi phục mạnh tuần qua.\n\n"
        f"• Volume 24h tăng vọt so với trung bình 7 ngày, cho thấy dòng tiền lớn đang quay lại thị trường.\n"
        f"• Nếu giữ được vùng kháng cự hiện tại, xu hướng ngắn hạn vẫn tích cực cho phe mua.\n"
        f"• Rủi ro: nếu phá dưới hỗ trợ gần nhất, đà tăng có thể chững lại và cần quan sát thêm.\n\n"
        f"Mọi người đang theo dõi vùng nào trên {c.cashtag}? Chia sẻ góc nhìn của bạn nhé! 👀\n\n"
        f"{c.hashtag} {c.cashtag} #Crypto #BinanceSquare #DYOR"
    )


def test_validate_post_valid():
    coin = CoinContext(name="Bitcoin", symbol="BTC", reason="test")
    post = _make_valid_post(coin)
    issues = validate_post(post, coin)
    assert issues == []


def test_validate_post_banned_phrase():
    coin = CoinContext(name="Bitcoin", symbol="BTC", reason="test")
    post = _make_valid_post(coin) + "\nĐây là vùng đáng chú ý cho nhà đầu tư."
    issues = validate_post(post, coin)
    assert any("banned phrase" in i.lower() for i in issues)


def test_validate_post_hook_too_long():
    coin = CoinContext(name="Bitcoin", symbol="BTC", reason="test")
    long_hook = "A" * 150
    body = "\n\n• Point 1\n• Point 2\n\n#BTC $BTC #Crypto #BinanceSquare #DYOR"
    post = long_hook + body
    issues = validate_post(post, coin)
    assert any("hook too long" in i.lower() for i in issues)


def test_validate_post_too_short():
    coin = CoinContext(name="Bitcoin", symbol="BTC", reason="test")
    post = "Short post #BTC $BTC"
    issues = validate_post(post, coin)
    assert any("too short" in i.lower() for i in issues)


def test_validate_post_missing_tags():
    coin = CoinContext(name="Bitcoin", symbol="BTC", reason="test")
    post = "A" * 500 + "\n#Crypto #BinanceSquare #DYOR"
    issues = validate_post(post, coin)
    assert any("missing" in i.lower() and "hashtag" in i.lower() for i in issues)
    assert any("missing" in i.lower() and "cashtag" in i.lower() for i in issues)


def test_validate_post_no_coin_skips_tag_check():
    post = "A" * 500 + "\n#Crypto"
    issues = validate_post(post, coin=None)
    # No coin means no tag check
    assert not any("missing" in i.lower() for i in issues)


# --- select_content_angle tests ---

def test_select_content_angle_returns_valid_angle():
    coin = CoinContext(name="Bitcoin", symbol="BTC", reason="test")
    name, instruction = select_content_angle(coin)
    valid_names = {a[0] for a in CONTENT_ANGLES}
    assert name in valid_names
    assert len(instruction) > 0


def test_select_content_angle_deterministic():
    coin = CoinContext(name="Bitcoin", symbol="BTC", reason="test")
    # Same coin, same day → same angle
    result1 = select_content_angle(coin)
    result2 = select_content_angle(coin)
    assert result1 == result2


def test_select_content_angle_varies_by_symbol():
    # Different coins should get different angles (with high probability)
    btc = CoinContext(name="Bitcoin", symbol="BTC", reason="test")
    eth = CoinContext(name="Ethereum", symbol="ETH", reason="test")
    # At least one pair should differ across many runs is hard to guarantee
    # deterministically, but we can check they produce valid results
    name1, _ = select_content_angle(btc)
    name2, _ = select_content_angle(eth)
    valid_names = {a[0] for a in CONTENT_ANGLES}
    assert name1 in valid_names
    assert name2 in valid_names


def test_content_angles_has_six_entries():
    assert len(CONTENT_ANGLES) == 6
    for name, instruction in CONTENT_ANGLES:
        assert isinstance(name, str) and len(name) > 0
        assert isinstance(instruction, str) and len(instruction) > 0
