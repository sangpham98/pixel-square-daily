"""Unified history storage — SQLite backend with txt migration support."""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

from .logger import log

DB_PATH = Path(os.getenv("HISTORY_DB", str(Path(__file__).parent.parent / "history.db")))
LEGACY_TXT = Path(__file__).parent.parent / "sent_history.txt"


@dataclass
class HistoryEntry:
    id: int
    timestamp: str
    status: str
    coin_name: str
    coin_symbol: str
    angle: str
    square_url: str
    content: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    status TEXT DEFAULT '',
    coin_name TEXT DEFAULT '',
    coin_symbol TEXT DEFAULT '',
    angle TEXT DEFAULT '',
    square_url TEXT DEFAULT '',
    content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_timestamp ON posts(timestamp);
CREATE INDEX IF NOT EXISTS idx_posts_coin_symbol ON posts(coin_symbol);
"""


@contextmanager
def _connect() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def _parse_entry_block(ts_str: str, body: str) -> dict:
    """Parse a single history entry block into a dict."""
    status = ""
    coin_name = ""
    coin_symbol = ""
    angle = ""
    square_url = ""

    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("Status:"):
            status = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Coin:"):
            m = re.match(r"Coin:\s*(.+?)\s*\(\$([A-Za-z0-9]+)\)", stripped)
            if m:
                coin_name = m.group(1).strip()
                coin_symbol = m.group(2).upper()
        elif stripped.startswith("Angle:"):
            angle = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("SquareURL:"):
            square_url = stripped.split(":", 1)[1].strip()

    # Extract content (everything after === POST THƯỜNG === or === ARTICLE ===)
    content = body
    marker_match = re.search(r"=== POST THƯỜNG ===\s*\n", body)
    if marker_match:
        content = body[marker_match.end():].strip()

    return {
        "timestamp": ts_str,
        "status": status,
        "coin_name": coin_name,
        "coin_symbol": coin_symbol,
        "angle": angle,
        "square_url": square_url,
        "content": content,
    }


def migrate_from_txt() -> int:
    """Migrate legacy sent_history.txt into SQLite. Returns number of entries migrated."""
    if not LEGACY_TXT.exists():
        return 0

    text = LEGACY_TXT.read_text(encoding="utf-8", errors="ignore")
    pattern = r"\n--- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ---\n"
    parts = re.split(pattern, text)

    entries: list[dict] = []
    for i in range(1, len(parts) - 1, 2):
        ts_str = parts[i]
        body = parts[i + 1]
        entries.append(_parse_entry_block(ts_str, body))

    if not entries:
        return 0

    init_db()
    with _connect() as conn:
        # Check if data already exists
        count = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        if count > 0:
            log.info("SQLite already has %d entries, skipping migration", count)
            return 0

        conn.executemany(
            """INSERT INTO posts (timestamp, status, coin_name, coin_symbol, angle, square_url, content)
               VALUES (:timestamp, :status, :coin_name, :coin_symbol, :angle, :square_url, :content)""",
            entries,
        )

    log.info("Migrated %d entries from %s to SQLite", len(entries), LEGACY_TXT.name)
    return len(entries)


def append_history(
    timestamp: str,
    coin_name: str,
    coin_symbol: str,
    content: str,
    status: str = "",
    angle: str = "",
    square_url: str = "",
) -> None:
    """Append a new history entry to SQLite."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO posts (timestamp, status, coin_name, coin_symbol, angle, square_url, content)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, status, coin_name, coin_symbol, angle, square_url, content),
        )


def load_history_entries(limit: int = 20) -> list[HistoryEntry]:
    """Load the most recent history entries."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, timestamp, status, coin_name, coin_symbol, angle, square_url, content "
            "FROM posts ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [HistoryEntry(**dict(r)) for r in reversed(rows)]


def recent_coin_symbols(hours: int = 48, limit: int = 10) -> set[str]:
    """Return coin symbols used in recent history (time-based or count-based)."""
    init_db()
    with _connect() as conn:
        if hours > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
            rows = conn.execute(
                "SELECT DISTINCT coin_symbol FROM posts WHERE coin_symbol != '' AND timestamp >= ?",
                (cutoff,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT coin_symbol FROM posts WHERE coin_symbol != '' ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return {r["coin_symbol"].upper() for r in rows}


def recent_history_texts(limit: int = 5) -> list[str]:
    """Return raw content of recent entries for similarity checking."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT content FROM posts ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [r["content"] for r in reversed(rows)]


def latest_history_time() -> str | None:
    """Return the timestamp of the most recent entry, or None."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT timestamp FROM posts ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return row["timestamp"] if row else None


def angle_distribution() -> dict[str, int]:
    """Return count of posts per angle."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT angle, COUNT(*) as cnt FROM posts WHERE angle != '' GROUP BY angle ORDER BY cnt DESC"
        ).fetchall()
    return {r["angle"]: r["cnt"] for r in rows}


def total_posts() -> int:
    """Return total number of history entries."""
    init_db()
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
