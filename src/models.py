"""Shared data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SquarePost:
    title: str
    url: str
    snippet: str


@dataclass
class DraftQueueItem:
    coin_symbol: str
    coin_name: str
    coin_reason: str
    draft: str
    short_post: str
    created_at: str
    angle: str = ""
