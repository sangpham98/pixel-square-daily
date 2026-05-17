"""Unit tests for draft queue and batch generation."""

from pathlib import Path
from unittest.mock import patch

from src.coin_selector import CoinContext
from src.models import DraftQueueItem
from src.draft_queue import delete_draft_by_index, generate_draft_batch, load_draft_queue, save_draft_queue


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


def test_delete_draft_by_index_removes_selected_item(tmp_path: Path):
    items = [_make_item("BTC", "Bitcoin"), _make_item("ETH", "Ethereum"), _make_item("SOL", "Solana")]
    with patch("src.draft_queue.DRAFT_QUEUE_FILE", tmp_path / "queue.json"):
        save_draft_queue(items)
        deleted, error = delete_draft_by_index(2)
        loaded = load_draft_queue()

    assert error is None
    assert deleted and deleted.coin_symbol == "ETH"
    assert [item.coin_symbol for item in loaded] == ["BTC", "SOL"]


def test_delete_draft_by_index_rejects_invalid_index(tmp_path: Path):
    items = [_make_item("BTC", "Bitcoin")]
    with patch("src.draft_queue.DRAFT_QUEUE_FILE", tmp_path / "queue.json"):
        save_draft_queue(items)
        deleted, error = delete_draft_by_index(2)
        loaded = load_draft_queue()

    assert deleted is None
    assert error == "Không có draft #2"
    assert [item.coin_symbol for item in loaded] == ["BTC"]


def test_delete_draft_by_index_handles_empty_queue(tmp_path: Path):
    with patch("src.draft_queue.DRAFT_QUEUE_FILE", tmp_path / "queue.json"):
        deleted, error = delete_draft_by_index(1)

    assert deleted is None
    assert error == "Queue trống"



def test_generate_draft_batch_excludes_already_selected_symbols(tmp_path: Path):
    seen_exclusions: list[set[str]] = []
    coins = [
        CoinContext(name="Bitcoin", symbol="BTC", reason="test"),
        CoinContext(name="Ethereum", symbol="ETH", reason="test"),
        CoinContext(name="Solana", symbol="SOL", reason="test"),
    ]

    def fake_build_draft_with_similarity(mode: str, excluded_symbols: set[str]):
        assert mode == "short"
        seen_exclusions.append(set(excluded_symbols))
        coin = next(coin for coin in coins if coin.symbol not in excluded_symbols)
        draft = f"=== POST THƯỜNG ===\nPost for {coin.name}\n{coin.hashtag} {coin.cashtag} #Crypto #BinanceSquare #DYOR"
        return draft, [], False, 0.0, 0, coin, "Market Watch"

    with (
        patch("src.draft_queue.DRAFT_QUEUE_FILE", tmp_path / "queue.json"),
        patch("src.draft_generator.build_draft_with_similarity", side_effect=fake_build_draft_with_similarity),
    ):
        queue = generate_draft_batch(count=3)

    assert [item.coin_symbol for item in queue] == ["BTC", "ETH", "SOL"]
    assert seen_exclusions == [set(), {"BTC"}, {"BTC", "ETH"}]
