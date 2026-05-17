"""Unit tests for coin_selector module."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from pathlib import Path

from src.coin_selector import (
    CoinContext,
    score_coin,
    coin_from_market_row,
)
from src.history import recent_coin_symbols, append_history, init_db


def test_coin_context_properties():
    coin = CoinContext(
        name="Bitcoin",
        symbol="BTC",
        reason="test",
        price=50000.0,
        change_24h=5.2,
        market_cap_rank=1,
    )

    assert coin.cashtag == "$BTC"
    assert coin.hashtag == "#BTC"
    assert coin.required_tags == ("#BTC", "$BTC")


def test_coin_context_hashtag_cleaning():
    # Test with special characters in symbol
    coin = CoinContext(name="Test", symbol="BTC-USD", reason="test")
    assert coin.hashtag == "#BTCUSD"

    # Test with lowercase
    coin = CoinContext(name="Test", symbol="eth", reason="test")
    assert coin.hashtag == "#ETH"

    # Test with empty symbol
    coin = CoinContext(name="Test", symbol="", reason="test")
    assert coin.hashtag == "#Crypto"


def test_score_coin():
    trending_symbols = {"BTC", "ETH", "SOL"}

    # Test trending coin with good rank
    coin = CoinContext(
        name="Bitcoin",
        symbol="BTC",
        reason="test",
        market_cap_rank=1,
        volume_24h=50_000_000_000,
        change_24h=5.0,
    )
    score = score_coin(coin, trending_symbols)
    # Should get: 45 (trending) + 25 (rank <=50) + 25 (volume) + 20 (change 3-18%) = 115
    assert score > 100

    # Test non-trending coin with poor rank
    coin = CoinContext(
        name="Unknown",
        symbol="UNK",
        reason="test",
        market_cap_rank=500,
        volume_24h=1_000_000,
        change_24h=1.0,
    )
    score = score_coin(coin, trending_symbols)
    # Should get minimal score
    assert score < 10

    # Test high volatility penalty
    coin = CoinContext(
        name="Volatile",
        symbol="VOL",
        reason="test",
        market_cap_rank=50,
        volume_24h=100_000_000,
        change_24h=50.0,  # Too high
    )
    score = score_coin(coin, trending_symbols)
    # Should have penalty for change > 35%
    assert score < 50


def test_coin_from_market_row():
    row = {
        "name": "Bitcoin",
        "symbol": "btc",
        "current_price": 50000.0,
        "price_change_percentage_24h": 5.2,
        "market_cap_rank": 1,
        "total_volume": 30_000_000_000,
        "market_cap": 1_000_000_000_000,
        "high_24h": 51000.0,
        "low_24h": 49000.0,
    }

    coin = coin_from_market_row(row)

    assert coin.name == "Bitcoin"
    assert coin.symbol == "BTC"
    assert coin.price == 50000.0
    assert coin.change_24h == 5.2
    assert coin.market_cap_rank == 1
    assert coin.volume_24h == 30_000_000_000
    assert coin.market_cap == 1_000_000_000_000
    assert coin.high_24h == 51000.0
    assert coin.low_24h == 49000.0


def test_coin_from_market_row_missing_fields():
    # Test with minimal data
    row = {
        "name": "Test Coin",
        "symbol": "test",
    }

    coin = coin_from_market_row(row)

    assert coin.name == "Test Coin"
    assert coin.symbol == "TEST"
    assert coin.price is None
    assert coin.change_24h is None
    assert coin.market_cap_rank is None


def test_score_coin_edge_cases():
    trending_symbols = set()

    # Test with None values
    coin = CoinContext(
        name="Test",
        symbol="TEST",
        reason="test",
        market_cap_rank=None,
        volume_24h=None,
        change_24h=None,
    )
    score = score_coin(coin, trending_symbols)
    # Should handle None gracefully
    assert score >= 0

    # Test optimal change range (3-18%)
    coin = CoinContext(
        name="Test",
        symbol="TEST",
        reason="test",
        market_cap_rank=50,
        volume_24h=100_000_000,
        change_24h=10.0,  # Optimal range
    )
    score = score_coin(coin, trending_symbols)
    assert score > 40  # Should get bonus for optimal change


# --- recent_coin_symbols tests (SQLite-based) ---

@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Use a temporary SQLite database for each test."""
    db_path = tmp_path / "test_history.db"
    monkeypatch.setattr("src.history.DB_PATH", db_path)
    # Also reset the module-level connection state by re-initializing
    from src import history
    history.DB_PATH = db_path
    init_db()
    yield


def test_recent_coin_symbols_time_based_excludes_old_entries():
    """Entries older than the time window should be excluded."""
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    old = (now - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S")

    append_history(recent, "Ethereum", "ETH", "draft content", status="posted")
    append_history(old, "Bitcoin", "BTC", "draft content", status="posted")

    symbols = recent_coin_symbols(hours=48)

    assert "ETH" in symbols
    assert "BTC" not in symbols


def test_recent_coin_symbols_time_based_includes_all_within_window():
    """All entries within the time window should be included, regardless of count."""
    now = datetime.now(timezone.utc)
    for i in range(15):
        ts = (now - timedelta(hours=i * 2)).strftime("%Y-%m-%d %H:%M:%S")
        append_history(ts, f"Coin{i}", f"COIN{i}", "draft content", status="posted")

    symbols = recent_coin_symbols(hours=48)

    # All 15 entries are within 48h (last one at 28h ago)
    assert len(symbols) == 15


def test_recent_coin_symbols_limit_fallback_when_hours_zero():
    """When hours=0, falls back to limit-based counting."""
    now = datetime.now(timezone.utc)
    for i in range(5):
        ts = (now - timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S")
        append_history(ts, f"Coin{i}", f"COIN{i}", "draft content", status="posted")

    symbols = recent_coin_symbols(hours=0, limit=3)

    assert len(symbols) == 3


def test_recent_coin_symbols_empty_db():
    """Empty database should return empty set."""
    symbols = recent_coin_symbols(hours=48)
    assert symbols == set()


def test_recent_coin_symbols_deduplicates():
    """Same coin appearing multiple times within window should be returned once."""
    now = datetime.now(timezone.utc)
    ts1 = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    ts2 = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    ts3 = (now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

    append_history(ts1, "Bitcoin", "BTC", "draft 1", status="posted")
    append_history(ts2, "Bitcoin", "BTC", "draft 2", status="posted")
    append_history(ts3, "Ethereum", "ETH", "draft 3", status="posted")

    symbols = recent_coin_symbols(hours=48)

    assert symbols == {"BTC", "ETH"}
