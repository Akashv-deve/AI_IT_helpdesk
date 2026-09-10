"""SQLite database for conversation history and support tickets."""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "helpdesk.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_query TEXT NOT NULL,
            decision TEXT,
            tool_name TEXT,
            tool_result TEXT,
            final_response TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE NOT NULL,
            user_query TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'open',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_conversation(
    user_query: str,
    decision: str,
    tool_name: str,
    tool_result: str,
    final_response: str,
) -> int:
    """Save a conversation turn. Returns row id."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute(
        """
        INSERT INTO conversations (user_query, decision, tool_name, tool_result, final_response, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_query, decision, tool_name, tool_result, final_response, now),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def create_ticket(user_query: str, description: str = "") -> str:
    """Create a support ticket and return ticket_id."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    # Simple ticket ID based on timestamp
    ticket_id = f"TKT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    try:
        cur.execute(
            """
            INSERT INTO support_tickets (ticket_id, user_query, description, status, created_at)
            VALUES (?, ?, ?, 'open', ?)
            """,
            (ticket_id, user_query, description or user_query, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Extremely rare collision; append random suffix
        import random
        ticket_id = f"TKT-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{random.randint(100,999)}"
        cur.execute(
            """
            INSERT INTO support_tickets (ticket_id, user_query, description, status, created_at)
            VALUES (?, ?, ?, 'open', ?)
            """,
            (ticket_id, user_query, description or user_query, now),
        )
        conn.commit()
    finally:
        conn.close()
    return ticket_id


def get_recent_conversations(limit: int = 5) -> List[Dict[str, Any]]:
    """Return recent conversation records."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM conversations ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# Initialize on import
init_db()
