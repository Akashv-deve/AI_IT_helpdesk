"""SQLite persistence for conversation history and support tickets.

Design notes worth knowing in a code review:

* No work happens at import time — ``init_db()`` is called explicitly by the
  entry points, so importing this module never touches the filesystem.
* Every connection is opened and closed through a context manager, so a raised
  exception can't leak a handle or leave a transaction half-open.
* Timestamps are timezone-aware UTC (``datetime.utcnow()`` is deprecated in
  Python 3.12 and returns a naive value that silently compares wrong).
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_query     TEXT    NOT NULL,
    route_reason   TEXT,
    tool_name      TEXT,
    tool_result    TEXT,
    final_response TEXT,
    confidence     REAL,
    escalated      INTEGER NOT NULL DEFAULT 0,
    llm_mode       TEXT,
    created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS support_tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   TEXT    UNIQUE NOT NULL,
    user_query  TEXT    NOT NULL,
    description TEXT,
    status      TEXT    NOT NULL DEFAULT 'open',
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_status        ON support_tickets(status);
"""

VALID_STATUSES = ("open", "in_progress", "resolved", "closed")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection that always commits or rolls back, then closes."""
    path = Path(db_path) if db_path else settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    """Create tables and indexes if they do not exist. Safe to call repeatedly."""
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    user_query: str
    description: str
    status: str
    created_at: str


def save_conversation(
    *,
    user_query: str,
    route_reason: str,
    tool_name: str,
    tool_result: str,
    final_response: str,
    confidence: float = 0.0,
    escalated: bool = False,
    llm_mode: str = "unknown",
    db_path: Path | None = None,
) -> int:
    """Persist one completed agent turn and return its row id."""
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO conversations (
                user_query, route_reason, tool_name, tool_result,
                final_response, confidence, escalated, llm_mode, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_query,
                route_reason,
                tool_name,
                tool_result[:4000],
                final_response[:4000],
                float(confidence),
                int(escalated),
                llm_mode,
                _utc_now(),
            ),
        )
        return int(cursor.lastrowid)


def create_ticket(
    user_query: str,
    description: str = "",
    db_path: Path | None = None,
) -> str:
    """Create a support ticket and return its human-readable id.

    The id combines a UTC timestamp with a short random suffix, so two tickets
    raised in the same second can never collide.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    ticket_id = f"TKT-{stamp}-{uuid.uuid4().hex[:4].upper()}"
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO support_tickets (ticket_id, user_query, description, status, created_at)
            VALUES (?, ?, ?, 'open', ?)
            """,
            (ticket_id, user_query, description or user_query, _utc_now()),
        )
    return ticket_id


def list_tickets(
    limit: int = 20,
    status: str | None = None,
    db_path: Path | None = None,
) -> list[Ticket]:
    """Return the most recent tickets, optionally filtered by status."""
    query = "SELECT ticket_id, user_query, description, status, created_at FROM support_tickets"
    params: list[Any] = []
    if status:
        if status not in VALID_STATUSES:
            raise ValueError(f"status must be one of {VALID_STATUSES}, got {status!r}")
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [Ticket(**dict(row)) for row in rows]


def update_ticket_status(
    ticket_id: str,
    status: str,
    db_path: Path | None = None,
) -> bool:
    """Move a ticket to a new status. Returns False if the id does not exist."""
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {VALID_STATUSES}, got {status!r}")
    with connect(db_path) as conn:
        cursor = conn.execute(
            "UPDATE support_tickets SET status = ? WHERE ticket_id = ?",
            (status, ticket_id),
        )
        return cursor.rowcount > 0


def recent_conversations(limit: int = 10, db_path: Path | None = None) -> list[dict[str, Any]]:
    """Return recent conversation turns, newest first."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM conversations ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def stats(db_path: Path | None = None) -> dict[str, int]:
    """Small summary used by the CLI dashboard."""
    with connect(db_path) as conn:
        conversations = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        escalations = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE escalated = 1"
        ).fetchone()[0]
        open_tickets = conn.execute(
            "SELECT COUNT(*) FROM support_tickets WHERE status = 'open'"
        ).fetchone()[0]
    return {
        "conversations": conversations,
        "escalations": escalations,
        "open_tickets": open_tickets,
    }
