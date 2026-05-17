"""Binance Square API integration."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

from .logger import log
from .utils import env, mask_key


USER_KEYS_FILE = Path(__file__).parent.parent / "user_square_keys.json"
BINANCE_SQUARE_POST_URL = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add"


def load_user_keys() -> dict[str, str]:
    try:
        if USER_KEYS_FILE.exists():
            data = json.loads(USER_KEYS_FILE.read_text(encoding="utf-8"))
            return {str(k): str(v) for k, v in data.items() if v}
    except Exception as exc:
        log.warning("Failed to load user Square keys: %s", exc)
    return {}


def save_user_keys(keys: dict[str, str]) -> None:
    USER_KEYS_FILE.write_text(json.dumps(keys, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        USER_KEYS_FILE.chmod(0o600)
    except Exception as exc:
        log.warning("Failed to chmod user key file: %s", exc)


def get_user_square_key(user_id: int | str | None) -> str:
    if user_id is not None:
        key = load_user_keys().get(str(user_id), "").strip()
        if key:
            return key
    return env("BINANCE_SQUARE_OPENAPI_KEY")


def set_user_square_key(user_id: int | str, api_key: str) -> str:
    api_key = api_key.strip()
    if len(api_key) < 20 or any(ch.isspace() for ch in api_key):
        raise ValueError("API key không hợp lệ: key quá ngắn hoặc có khoảng trắng")
    keys = load_user_keys()
    keys[str(user_id)] = api_key
    save_user_keys(keys)
    return mask_key(api_key)


def has_user_square_key(user_id: int | str | None) -> bool:
    return bool(user_id is not None and load_user_keys().get(str(user_id)))


def post_to_binance_square(body_text: str, user_id: int | str | None = None) -> str | None:
    auto_post = env("BINANCE_AUTO_POST_SHORT", "false").lower() in {"1", "true", "yes"}
    api_key = get_user_square_key(user_id)
    if not auto_post:
        return None
    if not api_key:
        raise RuntimeError("Chưa có Binance Square OpenAPI key. Bấm 🔑 Set API key trước khi đăng.")
    if len(body_text) < 100:
        raise RuntimeError("Short post is under 100 characters; refusing to auto-post")
    if not re.search(r"#[A-Za-z0-9]+", body_text) or not re.search(r"\$[A-Za-z0-9]+", body_text):
        raise RuntimeError("Short post is missing hashtag/cashtag; refusing to auto-post")

    headers = {
        "X-Square-OpenAPI-Key": api_key,
        "Content-Type": "application/json",
        "clienttype": "binanceSkill",
    }
    response = requests.post(
        BINANCE_SQUARE_POST_URL,
        headers=headers,
        json={"bodyTextOnly": body_text},
        timeout=40,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("code") != "000000" or not data.get("success", True):
        raise RuntimeError(f"Binance Square post failed: {data}")

    post_id = (data.get("data") or {}).get("id")
    if not post_id:
        return None
    return f"https://www.binance.com/square/post/{post_id}"
