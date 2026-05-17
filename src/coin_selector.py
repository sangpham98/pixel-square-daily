"""Coin selection logic for hot/trending coins."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests

from .cache import APICache
from .history import recent_coin_symbols
from .logger import log
from .utils import to_float, compact_usd


COIN_RECENT_EXCLUDE_COUNT = 10
COIN_RECENT_EXCLUDE_HOURS = int(os.getenv("COIN_RECENT_EXCLUDE_HOURS", "48"))
CACHE_FILE = Path(__file__).parent.parent / "coingecko_cache.json"
CACHE_TTL = 300  # 5 minutes

# Initialize cache
_api_cache = APICache(CACHE_FILE, default_ttl=CACHE_TTL)


@dataclass
class CoinContext:
    name: str
    symbol: str
    reason: str
    price: float | None = None
    change_24h: float | None = None
    market_cap_rank: int | None = None
    volume_24h: float | None = None
    market_cap: float | None = None
    high_24h: float | None = None
    low_24h: float | None = None
    data_quality: str = "partial"

    @property
    def cashtag(self) -> str:
        return f"${self.symbol.upper()}"

    @property
    def hashtag(self) -> str:
        clean = re.sub(r"[^A-Za-z0-9]", "", self.symbol.upper())
        return f"#{clean or 'Crypto'}"

    @property
    def required_tags(self) -> tuple[str, str]:
        return (self.hashtag, self.cashtag)


def coin_from_market_row(row: dict, reason: str | None = None, data_quality: str = "market") -> CoinContext:
    change = to_float(row.get("price_change_percentage_24h"))
    volume = to_float(row.get("total_volume"))
    rank = row.get("market_cap_rank")
    reason_text = reason or (f"24h change {change:+.2f}%, volume {compact_usd(volume)}" if change is not None else "CoinGecko market data")
    return CoinContext(
        name=row.get("name") or row.get("id") or "Unknown",
        symbol=(row.get("symbol") or "").upper(),
        reason=reason_text,
        price=to_float(row.get("current_price")),
        change_24h=change,
        market_cap_rank=int(rank) if isinstance(rank, int) else rank,
        volume_24h=volume,
        market_cap=to_float(row.get("market_cap")),
        high_24h=to_float(row.get("high_24h")),
        low_24h=to_float(row.get("low_24h")),
        data_quality=data_quality,
    )


def score_coin(coin: CoinContext, trending_symbols: set[str]) -> float:
    rank = coin.market_cap_rank or 999999
    volume = coin.volume_24h or 0
    change = abs(coin.change_24h or 0)
    score = 0.0
    if coin.symbol.upper() in trending_symbols:
        score += 45
    if rank <= 50:
        score += 25
    elif rank <= 100:
        score += 18
    elif rank <= 200:
        score += 10
    score += min(volume / 100_000_000, 25)
    if 3 <= change <= 18:
        score += 20
    elif 18 < change <= 35:
        score += 10
    elif change > 35:
        score -= 10
    return score


def enrich_trending_with_market_data(candidates: list[CoinContext]) -> list[CoinContext]:
    symbols = [coin.symbol.lower() for coin in candidates if coin.symbol]
    if not symbols:
        return candidates

    # Create cache key
    cache_key = f"markets_symbols_{','.join(sorted(set(symbols)))}"

    # Try cache first
    markets = _api_cache.get(cache_key)
    if markets is None:
        try:
            log.debug("Cache miss: fetching trending market data from CoinGecko")
            markets = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency":"usd","symbols":",".join(sorted(set(symbols))),"order":"market_cap_desc","per_page":100,"page":1,"sparkline":"false","price_change_percentage":"24h"},
                timeout=15,
            ).json()
            _api_cache.set(cache_key, markets)
        except Exception as exc:
            log.error("Trending market enrichment failed: %s", exc)
            return candidates
    else:
        log.debug("Cache hit: using cached trending market data")

    by_symbol = {str(row.get("symbol", "")).upper(): row for row in markets if row.get("symbol")}
    enriched: list[CoinContext] = []
    for coin in candidates:
        row = by_symbol.get(coin.symbol.upper())
        if row:
            enriched.append(coin_from_market_row(row, reason=f"CoinGecko trending search + market data ({coin.reason})", data_quality="trending+market"))
        else:
            enriched.append(coin)
    return enriched


def select_hot_coin(excluded_symbols: Iterable[str] | None = None) -> CoinContext:
    """Pick a hot coin with enough market quality, excluding recent history."""
    candidates: list[CoinContext] = []
    trending_symbols: set[str] = set()
    extra_excluded_symbols = {symbol.upper() for symbol in excluded_symbols or []}

    # Fetch trending coins with cache
    cache_key_trending = "trending_coins"
    trending_data = _api_cache.get(cache_key_trending)
    if trending_data is None:
        try:
            log.debug("Cache miss: fetching trending coins from CoinGecko")
            trending_data = requests.get("https://api.coingecko.com/api/v3/search/trending", timeout=12).json().get("coins", [])
            _api_cache.set(cache_key_trending, trending_data)
        except Exception as exc:
            log.error("Trending coin fetch failed: %s", exc)
            trending_data = []
    else:
        log.debug("Cache hit: using cached trending coins")

    for item in trending_data[:10]:
        coin = item.get("item", {})
        name = coin.get("name") or coin.get("id") or "Unknown"
        symbol = (coin.get("symbol") or name[:6]).upper()
        rank = coin.get("market_cap_rank")
        trending_symbols.add(symbol)
        candidates.append(CoinContext(name=name, symbol=symbol, reason="CoinGecko trending search", market_cap_rank=rank, data_quality="trending"))

    candidates = enrich_trending_with_market_data(candidates)

    # Fetch market movers with cache
    cache_key_markets = "markets_volume_desc"
    markets = _api_cache.get(cache_key_markets)
    if markets is None:
        try:
            log.debug("Cache miss: fetching market data from CoinGecko")
            markets = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency":"usd","order":"volume_desc","per_page":80,"page":1,"sparkline":"false","price_change_percentage":"24h"},
                timeout=15,
            ).json()
            _api_cache.set(cache_key_markets, markets)
        except Exception as exc:
            log.error("Market mover fetch failed: %s", exc)
            markets = []
    else:
        log.debug("Cache hit: using cached market data")

    for row in markets:
        change = to_float(row.get("price_change_percentage_24h"))
        rank = row.get("market_cap_rank") or 999999
        volume = to_float(row.get("total_volume")) or 0
        if change is None:
            continue
        if rank <= 200 and (abs(change) >= 3 or volume >= 100_000_000):
            candidates.append(coin_from_market_row(
                row,
                reason=f"24h change {change:+.2f}%, volume {compact_usd(volume)}, rank #{rank}",
                data_quality="market",
            ))

    best_by_symbol: dict[str, CoinContext] = {}
    for coin in candidates:
        symbol = coin.symbol.upper()
        if not symbol:
            continue
        current = best_by_symbol.get(symbol)
        if current is None or score_coin(coin, trending_symbols) > score_coin(current, trending_symbols):
            best_by_symbol[symbol] = coin

    if best_by_symbol:
        recent_symbols = recent_coin_symbols(hours=COIN_RECENT_EXCLUDE_HOURS, limit=COIN_RECENT_EXCLUDE_COUNT)
        excluded = recent_symbols | extra_excluded_symbols
        unique = sorted(best_by_symbol.values(), key=lambda coin: score_coin(coin, trending_symbols), reverse=True)
        eligible = [coin for coin in unique if coin.symbol.upper() not in excluded]
        pool = eligible or [coin for coin in unique if coin.symbol.upper() not in extra_excluded_symbols] or unique
        selected = pool[0]
        score = score_coin(selected, trending_symbols)
        if selected.symbol.upper() in recent_symbols:
            selected.reason = f"{selected.reason}; quality score {score:.1f}; fallback because all candidates were used in last {COIN_RECENT_EXCLUDE_HOURS}h"
        else:
            selected.reason = f"{selected.reason}; quality score {score:.1f}; not used in last {COIN_RECENT_EXCLUDE_HOURS}h"
        return selected
    return CoinContext(name="Bitcoin", symbol="BTC", reason="fallback: most popular crypto asset", data_quality="fallback")
