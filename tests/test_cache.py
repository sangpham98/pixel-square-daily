"""Unit tests for cache module."""

import time
from pathlib import Path
import tempfile
import pytest
from src.cache import APICache, CacheEntry


def test_cache_entry_expiration():
    # Test non-expired entry
    entry = CacheEntry(data="test", timestamp=time.time(), ttl=300)
    assert not entry.is_expired()

    # Test expired entry
    entry = CacheEntry(data="test", timestamp=time.time() - 400, ttl=300)
    assert entry.is_expired()


def test_cache_set_and_get():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_cache.json"
        cache = APICache(cache_file, default_ttl=300)

        # Set and get value
        cache.set("key1", {"data": "value1"})
        result = cache.get("key1")
        assert result == {"data": "value1"}

        # Get non-existent key
        result = cache.get("nonexistent")
        assert result is None


def test_cache_expiration():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_cache.json"
        cache = APICache(cache_file, default_ttl=1)  # 1 second TTL

        # Set value
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(1.5)
        result = cache.get("key1")
        assert result is None


def test_cache_custom_ttl():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_cache.json"
        cache = APICache(cache_file, default_ttl=300)

        # Set with custom TTL
        cache.set("key1", "value1", ttl=1)
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(1.5)
        assert cache.get("key1") is None


def test_cache_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_cache.json"

        # Create cache and set value
        cache1 = APICache(cache_file, default_ttl=300)
        cache1.set("key1", "value1")
        cache1.set("key2", {"nested": "data"})

        # Create new cache instance (simulates restart)
        cache2 = APICache(cache_file, default_ttl=300)
        assert cache2.get("key1") == "value1"
        assert cache2.get("key2") == {"nested": "data"}


def test_cache_clear_expired():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_cache.json"
        cache = APICache(cache_file, default_ttl=1)

        # Set multiple values
        cache.set("key1", "value1", ttl=1)
        cache.set("key2", "value2", ttl=300)
        cache.set("key3", "value3", ttl=1)

        # Wait for some to expire
        time.sleep(1.5)

        # Clear expired
        removed = cache.clear_expired()
        assert removed == 2

        # Check remaining
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") is None


def test_cache_clear_all():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_cache.json"
        cache = APICache(cache_file, default_ttl=300)

        # Set values
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        # Clear all
        cache.clear_all()

        # Verify empty
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert not cache_file.exists()


def test_cache_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_cache.json"
        cache = APICache(cache_file, default_ttl=1)

        # Set values with different TTLs
        cache.set("key1", "value1", ttl=1)
        cache.set("key2", "value2", ttl=300)

        # Check stats before expiration
        stats = cache.stats()
        assert stats["total_entries"] == 2
        assert stats["active_entries"] == 2

        # Wait for expiration
        time.sleep(1.5)

        # Check stats after expiration
        stats = cache.stats()
        assert stats["total_entries"] == 2
        assert stats["expired_entries"] == 1
        assert stats["active_entries"] == 1


def test_cache_overwrite():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_cache.json"
        cache = APICache(cache_file, default_ttl=300)

        # Set initial value
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Overwrite
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"


def test_cache_complex_data():
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_cache.json"
        cache = APICache(cache_file, default_ttl=300)

        # Test with complex nested data
        complex_data = {
            "coins": [
                {"name": "Bitcoin", "symbol": "BTC", "price": 50000},
                {"name": "Ethereum", "symbol": "ETH", "price": 3000},
            ],
            "metadata": {
                "timestamp": 1234567890,
                "source": "coingecko",
            }
        }

        cache.set("complex", complex_data)
        result = cache.get("complex")
        assert result == complex_data
        assert result["coins"][0]["name"] == "Bitcoin"
