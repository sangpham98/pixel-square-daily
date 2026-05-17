"""Unit tests for draft queue and batch generation."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from src.models import DraftQueueItem
from src.draft_queue import load_draft_queue, save_draft_queue


def _make_item(symbol: str = "BTC", name: str = "Bitcoin") -> DraftQueueItem:
    return DraftQueueItem(
        coin_symbol=symbol,
        coin_name=name,
        coin_reason="test reason",
        draft=f"=== POST THƯỜNG ===\nTest draft for {name}\n#${symbol} ${symbol} #Crypto #BinanceSquare #DYOR",
        short_post=f"Test draft for {name}\n#${symbol} ${symbol} #Crypto #BinanceSquare #DYOR",
        created_at="2026-05-16 12:00:00",
    )


def test_load_empty_queue(tmp_path: Path):
    with patch("src.draft_queue.DRAFT_QUEUE_FILE", tmp_path / "queue.json"):
        queue = load_draft_queue()
    assert queue == []


def test_save_and_load_queue(tmp_path: Path):
    items = [_make_item("BTC", "Bitcoin"), _make_item("ETH", "Ethereum")]
    with patch("src.draft_queue.DRAFT_QUEUE_FILE", tmp_path / "queue.json"):
        save_draft_queue(items)
        loaded = load_draft_queue()

    assert len(loaded) == 2
    assert loaded[0].coin_symbol == "BTC"
    assert loaded[1].coin_symbol == "ETH"
    assert loaded[0].coin_name == "Bitcoin"


def test_load_corrupted_queue(tmp_path: Path):
    queue_file = tmp_path / "queue.json"
    queue_file.write_text("not valid json!!!")
    with patch("src.draft_queue.DRAFT_QUEUE_FILE", queue_file):
        queue = load_draft_queue()
    assert queue == []


def test_queue_roundtrip_preserves_all_fields(tmp_path: Path):
    item = _make_item()
    with patch("src.draft_queue.DRAFT_QUEUE_FILE", tmp_path / "queue.json"):
        save_draft_queue([item])
        loaded = load_draft_queue()

    assert loaded[0].coin_symbol == item.coin_symbol
    assert loaded[0].coin_name == item.coin_name
    assert loaded[0].coin_reason == item.coin_reason
    assert loaded[0].draft == item.draft
    assert loaded[0].short_post == item.short_post
    assert loaded[0].created_at == item.created_at
