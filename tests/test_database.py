"""Persistence: tickets, conversation history and the summary counters."""

from __future__ import annotations

import pytest

from helpdesk import database


def test_init_db_is_idempotent(tmp_path):
    db = tmp_path / "x.db"
    database.init_db(db)
    database.init_db(db)
    with database.connect(db) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row[0] for row in rows}
    assert {"conversations", "support_tickets"} <= names


def test_create_ticket_returns_prefixed_id(temp_db):
    ticket_id = database.create_ticket("printer on fire", db_path=temp_db)
    assert ticket_id.startswith("TKT-")
    assert len(ticket_id) > 12


def test_ticket_ids_are_unique_within_the_same_second(temp_db):
    ids = {database.create_ticket(f"issue {n}", db_path=temp_db) for n in range(50)}
    assert len(ids) == 50, "timestamp-only IDs would collide here"


def test_tickets_round_trip(temp_db):
    database.create_ticket("vpn down", "cannot reach the intranet", db_path=temp_db)
    tickets = database.list_tickets(db_path=temp_db)
    assert len(tickets) == 1
    assert tickets[0].user_query == "vpn down"
    assert tickets[0].status == "open"


def test_list_tickets_filters_by_status(temp_db):
    first = database.create_ticket("one", db_path=temp_db)
    database.create_ticket("two", db_path=temp_db)
    database.update_ticket_status(first, "resolved", db_path=temp_db)
    assert len(database.list_tickets(status="open", db_path=temp_db)) == 1
    assert len(database.list_tickets(status="resolved", db_path=temp_db)) == 1


def test_update_status_rejects_unknown_values(temp_db):
    ticket_id = database.create_ticket("one", db_path=temp_db)
    with pytest.raises(ValueError):
        database.update_ticket_status(ticket_id, "banana", db_path=temp_db)


def test_update_status_reports_missing_ticket(temp_db):
    assert database.update_ticket_status("TKT-nope", "closed", db_path=temp_db) is False


def test_save_conversation_and_read_back(temp_db):
    row_id = database.save_conversation(
        user_query="wifi down",
        route_reason="keyword match",
        tool_name="search_knowledge_base",
        tool_result="steps…",
        final_response="try restarting the router",
        confidence=0.82,
        escalated=False,
        llm_mode="offline (rule-based)",
        db_path=temp_db,
    )
    assert row_id > 0
    rows = database.recent_conversations(db_path=temp_db)
    assert rows[0]["user_query"] == "wifi down"
    assert rows[0]["confidence"] == pytest.approx(0.82)


def test_stats_counts_escalations(temp_db):
    database.save_conversation(
        user_query="q", route_reason="", tool_name="t", tool_result="",
        final_response="", confidence=0.1, escalated=True, db_path=temp_db,
    )
    database.create_ticket("q", db_path=temp_db)
    summary = database.stats(db_path=temp_db)
    assert summary == {"conversations": 1, "escalations": 1, "open_tickets": 1}


def test_connection_rolls_back_on_error(temp_db):
    with pytest.raises(RuntimeError), database.connect(temp_db) as conn:
        conn.execute(
            "INSERT INTO support_tickets (ticket_id, user_query, created_at) "
            "VALUES ('TKT-rollback', 'q', 'now')"
        )
        raise RuntimeError("boom")
    assert database.list_tickets(db_path=temp_db) == []


def test_timestamps_are_timezone_aware(temp_db):
    database.create_ticket("q", db_path=temp_db)
    created = database.list_tickets(db_path=temp_db)[0].created_at
    assert created.endswith("+00:00"), "timestamps must carry a UTC offset"
