"""API caching layer with TTL support."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .logger import log


@dataclass
class CacheEntry:
    data: Any
    timestamp: float
    ttl: int  # seconds

    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl


class APICache:
    """Simple file-based cache with TTL support."""

    def __init__(self, cache_file: Path, default_ttl: int = 300):
        self.cache_file = cache_file
        self.default_ttl = default_ttl
        self._memory_cache: dict[str, CacheEntry] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load cache from disk on initialization."""
        if not self.cache_file.exists():
            return
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            for key, entry_data in data.items():
                entry = CacheEntry(
                    data=entry_data["data"],
                    timestamp=entry_data["timestamp"],
                    ttl=entry_data["ttl"],
                )
                if not entry.is_expired():
                    self._memory_cache[key] = entry
        except Exception as exc:
            log.warning("Failed to load cache from disk: %s", exc)

    def _save_to_disk(self) -> None:
        """Save cache to disk."""
        try:
            data = {}
            for key, entry in self._memory_cache.items():
                if not entry.is_expired():
                    data[key] = {
                        "data": entry.data,
                        "timestamp": entry.timestamp,
                        "ttl": entry.ttl,
                    }
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            log.warning("Failed to save cache to disk: %s", exc)

    def get(self, key: str) -> Any | None:
        """Get cached value if not expired."""
        entry = self._memory_cache.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._memory_cache[key]
            return None
        return entry.data

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set cache value with TTL."""
        if ttl is None:
            ttl = self.default_ttl
        entry = CacheEntry(data=value, timestamp=time.time(), ttl=ttl)
        self._memory_cache[key] = entry
        self._save_to_disk()

    def clear_expired(self) -> int:
        """Remove expired entries and return count removed."""
        expired_keys = [key for key, entry in self._memory_cache.items() if entry.is_expired()]
        for key in expired_keys:
            del self._memory_cache[key]
        if expired_keys:
            self._save_to_disk()
        return len(expired_keys)

    def clear_all(self) -> None:
        """Clear all cache entries."""
        self._memory_cache.clear()
        if self.cache_file.exists():
            self.cache_file.unlink()

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = len(self._memory_cache)
        expired = sum(1 for entry in self._memory_cache.values() if entry.is_expired())
        return {
            "total_entries": total,
            "expired_entries": expired,
            "active_entries": total - expired,
        }
