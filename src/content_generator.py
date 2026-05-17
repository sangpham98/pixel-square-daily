"""Content generation with LLM and prompt building."""

from __future__ import annotations

import json
import re
from datetime import datetime
import requests

from .coin_selector import CoinContext
from .history import recent_history_texts
from .logger import log
from .utils import compact_usd, env


REQUIRED_TAGS: tuple[str, ...] = ()

BANNED_PHRASES: list[str] = [
    "đang vào vùng đáng chú ý vì có đủ 3 yếu tố",
    "vùng đáng chú ý",
    "đủ 3 yếu tố",
    "điểm cần xác nhận",
    "rủi ro chính",
    "phản ứng giá và dòng tiền",
    "theo dõi thêm phản ứng giá và dòng tiền trước khi quyết định",
    "anh em đang để mắt vùng nào",
    "chỉ là một pha FOMO",
]

SHORT_POST_MIN_CHARS = 450
SHORT_POST_MAX_CHARS = 900
HOOK_MAX_CHARS = 120


def load_recent_history(max_chars: int = 5000) -> str:
    texts = recent_history_texts(limit=10)
    if not texts:
        return ""
    combined = "\n---\n".join(texts)
    return combined[-max_chars:]


CONTENT_ANGLES: list[tuple[str, str]] = [
    ("Market Watch", "Tập trung biến động giá, volume, xu hướng ngắn hạn, tín hiệu cần xác nhận."),
    ("Narrative/Catalyst", "Tập trung câu chuyện thị trường, tin tức, hệ sinh thái, sự kiện hoặc lý do coin được chú ý."),
    ("Risk-first", "Tập trung rủi ro, điều kiện invalidation, tránh FOMO và điểm cần quan sát trước khi hành động."),
    ("Price Action", "Phân tích hành động giá: vùng hỗ trợ/kháng cự, volume profile, breakout breakdown."),
    ("On-chain / TVL", "Dữ kiện on-chain: TVL thay đổi, DEX volume, active address, inflow/outflow."),
    ("Catalyst Watch", "Catalyst cụ thể: unlock, listing, upgrade, airdrop — sự kiện sắp tới thúc đẩy giá."),
]


def select_content_angle(coin: CoinContext) -> tuple[str, str]:
    """Deterministic angle selection based on date + coin symbol."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    idx = hash(f"{date_str}:{coin.symbol.upper()}") % len(CONTENT_ANGLES)
    return CONTENT_ANGLES[idx]


def build_prompt(posts: list, coin: CoinContext, mode: str = "both") -> tuple[str, str]:
    # Build sources section
    source_lines = []
    for idx, post in enumerate(posts, 1):
        source_lines.append(f"{idx}. {post.title}\nURL: {post.url}\nSnippet: {post.snippet}")
    sources = "\n\n".join(source_lines) if source_lines else "(Không tìm được nguồn)"

    required_hashtag, required_cashtag = coin.required_tags
    angle_name, angle_instruction = select_content_angle(coin)

    coin_brief = (
        f"{coin.name} ({coin.cashtag}). "
        f"Giá: {compact_usd(coin.price)}, "
        f"24h: {coin.change_24h if coin.change_24h is not None else 'N/A'}%, "
        f"vùng 24h: {compact_usd(coin.low_24h)} - {compact_usd(coin.high_24h)}, "
        f"rank: {coin.market_cap_rank or 'N/A'}, "
        f"volume 24h: {compact_usd(coin.volume_24h)}, "
        f"market cap: {compact_usd(coin.market_cap)}."
    )

    recent_history = load_recent_history() or "(Chưa có bài cũ)"

    # Mode-specific output instruction
    if mode == "short":
        output_note = (
            "VIẾT 1 BÀI POST THƯỜNG. "
            "450-900 ký tự. "
            "Cấu trúc: hook 1 câu → 2-3 bullet → kết luận + CTA nhẹ. "
            "Tối đa 2 emoji. Dùng bullet `•`. Không dùng bảng markdown."
        )
    elif mode == "article":
        output_note = (
            "VIẾT 1 BÀI ARTICLE. Trên 500 ký tự. "
            "Cấu trúc: tiêu đề → mở bài → dữ kiện/tín hiệu → góc nhìn → kết luận. "
            "Dùng bullet khi liệt kê. Chừa dòng trắng giữa các phần."
        )
    else:
        output_note = (
            "VIẾT 1 BÀI POST THƯỜNG. "
            "450-900 ký tự. "
            "Cấu trúc: hook 1 câu → 2-3 bullet → kết luận + CTA nhẹ. "
            "Tối đa 2 emoji. Dùng bullet `•`. Không dùng bảng markdown."
        )

    prompt = f"""Bạn là crypto content creator tiếng Việt cho Binance Square.

TASK: Viết bài {output_note}

=== RULES (bắt buộc, đọc kỹ) ===
1. Chỉ dùng dữ kiện có trong phần "Nguồn" và "Thông tin coin" bên dưới. Không bịa số, giá, tin tức, partnership.
2. Không copy câu chữ từ nguồn. Không mô phỏng giọng văn cụ thể của nguồn.
3. Không trùng hook/bullet/cấu trúc với lịch sử bài đã gửi. Nếu không chắc: viết hoàn toàn khác.
4. Không hứa lợi nhuận, không kêu gọi mua/bán/all-in.
5. Không dùng bảng markdown. Tối đa 2 emoji.
6. Hook phải là câu đầu tiên, dưới 120 ký tự, tạo tò mò nhưng không clickbait.

=== CẤM TUYỆT ĐỐI (vi phạm = bài bị block) ===
- "đang vào vùng đáng chú ý vì có đủ 3 yếu tố"
- "vùng đáng chú ý", "đủ 3 yếu tố", "điểm cần xác nhận", "rủi ro chính"
- "phản ứng giá và dòng tiền", "theo dõi thêm phản ứng giá và dòng tiền trước khi quyết định"
- "anh em đang để mắt vùng nào", "chỉ là một pha FOMO"
Nếu thiếu ý tưởng: viết hook bằng câu hỏi, câu so sánh, hoặc góc vào tín hiệu cụ thể từ nguồn.

=== FORMAT OUTPUT ===
Format duy nhất, bắt đầu bằng:
=== POST THƯỜNG ===
[bài viết của bạn, có đủ 5 tags: {required_hashtag} {required_cashtag} #Crypto #BinanceSquare #DYOR]

=== Thông tin coin ===
{coin_brief}

=== Angle bài này ===
{angle_name}: {angle_instruction}

=== Nguồn tham khảo ===
{sources}

=== Lịch sử bài gần đây (tránh trùng) ===
{recent_history}
""".strip()
    return prompt, angle_name
    return prompt, angle_name


def llm_providers() -> list[dict[str, str]]:
    providers = [{
        "base_url": env("OPENAI_BASE_URL", "http://localhost:20128/v1"),
        "api_key": env("OPENAI_API_KEY", "not-needed"),
        "model": env("OPENAI_MODEL", "qw/qwen3-coder-plus"),
    }]

    fallback_json = env("OPENAI_FALLBACK_PROVIDERS")
    if fallback_json:
        try:
            for provider in json.loads(fallback_json):
                if isinstance(provider, dict) and provider.get("base_url") and provider.get("model"):
                    providers.append({
                        "base_url": str(provider["base_url"]),
                        "api_key": str(provider.get("api_key") or env("OPENAI_API_KEY", "not-needed")),
                        "model": str(provider["model"]),
                    })
        except Exception as exc:
            log.warning("Invalid OPENAI_FALLBACK_PROVIDERS JSON: %s", exc)

    fallback_base = env("FALLBACK_OPENAI_BASE_URL")
    fallback_model = env("FALLBACK_OPENAI_MODEL")
    if fallback_base and fallback_model:
        providers.append({
            "base_url": fallback_base,
            "api_key": env("FALLBACK_OPENAI_API_KEY", env("OPENAI_API_KEY", "not-needed")),
            "model": fallback_model,
        })

    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for provider in providers:
        base_url = provider["base_url"].rstrip("/")
        model = provider["model"]
        key = (base_url, model)
        if key in seen:
            continue
        seen.add(key)
        unique.append({**provider, "base_url": base_url})
    return unique


def call_llm_provider(prompt: str, provider: dict[str, str]) -> str:
    payload = {
        "model": provider["model"],
        "messages": [
            {"role": "system", "content": "Bạn viết nội dung crypto chuyên nghiệp, rõ ràng, không copy nguồn."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.75,
        "max_tokens": 1400,
    }
    headers = {"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"}
    response = requests.post(f"{provider['base_url']}/chat/completions", json=payload, headers=headers, timeout=120)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def call_llm(prompt: str, fallback_coin: CoinContext | None = None) -> str:
    errors: list[str] = []
    for provider in llm_providers():
        try:
            return call_llm_provider(prompt, provider)
        except Exception as exc:
            provider_name = f"{provider['base_url']} ({provider['model']})"
            errors.append(f"{provider_name}: {exc}")
            log.error("LLM provider failed: %s: %s", provider_name, exc)

    log.error("All LLM providers failed, using built-in fallback draft: %s", " | ".join(errors))
    return fallback_draft(fallback_coin)


def fallback_draft(coin: CoinContext | None = None) -> str:
    coin = coin or CoinContext(name="Bitcoin", symbol="BTC", reason="fallback")
    required_hashtag, required_cashtag = coin.required_tags
    return f"""=== POST THƯỜNG ===
{coin.name} ({required_cashtag}) đang thu hút sự chú ý với mức tăng {coin.change_24h if coin.change_24h else 'N/A'}% trong 24h qua.

• Khối lượng giao dịch: {compact_usd(coin.volume_24h)} — cho thấy dòng tiền đang quan tâm.
• Cần theo dõi: phản ứng ở vùng kháng cự tiếp theo trước khi xác nhận xu hướng.
• Rủi ro: nếu volume giảm mạnh, đà tăng có thể yếu đi nhanh.

Mọi người đang theo dõi tín hiệu nào trên {coin.cashtag}? 👀

{required_hashtag} {required_cashtag} #Crypto #BinanceSquare #DYOR"""


def split_draft_sections(text: str) -> list[str]:
    """Return POST THƯỜNG and ARTICLE bodies so each can be tag-validated."""
    sections: list[str] = []
    patterns = [
        r"===\s*POST THƯỜNG\s*===(.*?)(?====\s*ARTICLE\s*===|$)",
        r"===\s*ARTICLE\s*===(.*)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.S | re.I)
        if match:
            sections.append(match.group(1).strip())
    return sections


def append_missing_tags(text: str, required_tags: tuple[str, ...] | None = None) -> str:
    tags = required_tags or REQUIRED_TAGS
    missing = [tag for tag in tags if tag.lower() not in text.lower()]
    if not missing:
        return text
    return f"{text.rstrip()}\n\n{' '.join(missing)}"


def enforce_required_terms(text: str, required_tags: tuple[str, ...] | None = None) -> str:
    sections = split_draft_sections(text)
    if not sections:
        return append_missing_tags(text, required_tags)

    updated = text
    for section_text in sections:
        fixed_section = append_missing_tags(section_text, required_tags)
        updated = updated.replace(section_text, fixed_section, 1)
    return updated


def validate_post(content: str, coin: CoinContext | None = None) -> list[str]:
    """Check generated post against quality rules. Returns list of issues (empty = valid)."""
    issues: list[str] = []

    # Banned phrases
    lower = content.lower()
    for phrase in BANNED_PHRASES:
        if phrase.lower() in lower:
            issues.append(f"Contains banned phrase: {phrase}")

    # Hook length (first non-empty line)
    lines = [ln for ln in content.splitlines() if ln.strip()]
    if lines:
        hook = lines[0].strip()
        if len(hook) > HOOK_MAX_CHARS:
            issues.append(f"Hook too long: {len(hook)} chars (max {HOOK_MAX_CHARS})")

    # Character count
    char_count = len(content)
    if char_count < SHORT_POST_MIN_CHARS:
        issues.append(f"Post too short: {char_count} chars (min {SHORT_POST_MIN_CHARS})")
    elif char_count > SHORT_POST_MAX_CHARS:
        issues.append(f"Post too long: {char_count} chars (max {SHORT_POST_MAX_CHARS})")

    # Required tags
    if coin:
        hashtag, cashtag = coin.required_tags
        if hashtag.lower() not in lower:
            issues.append(f"Missing required hashtag: {hashtag}")
        if cashtag.lower() not in lower:
            issues.append(f"Missing required cashtag: {cashtag}")

    return issues


def extract_short_post(draft: str) -> str:
    match = re.search(r"===\s*POST THƯỜNG\s*===(.*?)(?:===\s*ARTICLE\s*===|$)", draft, re.S | re.I)
    if not match:
        return ""
    post = match.group(1).strip()
    return post


def extract_article(draft: str) -> str:
    match = re.search(r"===\s*ARTICLE\s*===(.*)$", draft, re.S | re.I)
    if not match:
        return ""
    return match.group(1).strip()
