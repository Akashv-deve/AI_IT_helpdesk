"""The service layer — everything a user interface can do, without a UI."""

from __future__ import annotations

import pytest

from helpdesk import database, knowledge_base, llm, tools
from helpdesk.service import MAX_QUERY_LENGTH, HelpdeskService


@pytest.fixture
def service(temp_db, monkeypatch):
    """A service wired to a throwaway database and the deterministic reasoner."""
    monkeypatch.setattr(database.settings, "db_path", temp_db, raising=False)
    monkeypatch.setattr(tools.database.settings, "db_path", temp_db, raising=False)
    return HelpdeskService(force_offline=True)


# --- initialisation ------------------------------------------------------


def test_service_starts_without_ollama(service):
    assert service.is_offline is True
    assert service.mode_label == "Offline fallback mode"
    assert "rule-based" in service.llm_mode


def test_construction_creates_the_schema(temp_db, monkeypatch):
    monkeypatch.setattr(database.settings, "db_path", temp_db, raising=False)
    HelpdeskService(force_offline=True)
    assert database.stats(temp_db) == {
        "conversations": 0,
        "escalations": 0,
        "open_tickets": 0,
    }


def test_agent_is_built_lazily(service):
    assert service._agent is None
    service.ask("my wifi is not connecting")
    assert service._agent is not None


# --- asking questions ----------------------------------------------------


def test_normal_query_is_answered_without_escalating(service):
    result = service.ask("my wifi is not connecting")
    assert result.ok
    assert result.answer
    assert result.escalated is False
    assert result.confidence > 0
    assert result.tool_name in tools.TOOLS


def test_answer_names_the_matched_article(service):
    """Tool metadata must survive the graph, or answers go generic."""
    result = service.ask("the printer is offline")
    assert "Printer" in result.answer


def test_unknown_query_escalates_with_a_ticket(service):
    result = service.ask("my quantum flux capacitor is misaligned")
    assert result.escalated is True
    assert result.ticket_id and result.ticket_id.startswith("TKT-")
    assert len(service.tickets()) == 1


def test_repeated_queries_in_one_session(service):
    first = service.ask("my wifi is not connecting")
    second = service.ask("the printer is offline")
    third = service.ask("i forgot my password")
    assert all(turn.ok for turn in (first, second, third))
    assert service.dashboard().conversations == 3
    assert len({turn.tool_name for turn in (first, second, third)}) >= 1


def test_every_turn_reports_its_reasoning_mode(service):
    result = service.ask("my wifi is not connecting")
    assert "rule-based" in result.llm_mode


@pytest.mark.parametrize("bad", ["", "   ", "\n\t "])
def test_empty_input_is_rejected_cleanly(service, bad):
    result = service.ask(bad)
    assert result.ok is False
    assert "describe the problem" in result.error.lower()
    assert service.dashboard().conversations == 0, "a rejected query must not be recorded"


def test_overlong_input_is_rejected(service):
    result = service.ask("x" * (MAX_QUERY_LENGTH + 1))
    assert result.ok is False
    assert "shorten" in result.error.lower()


def test_agent_failure_becomes_a_readable_message(service, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("graph exploded")

    monkeypatch.setattr("helpdesk.service.answer_query", explode)
    result = service.ask("my wifi is not connecting")
    assert result.ok is False
    assert "RuntimeError" in result.error
    assert "graph exploded" not in result.error, "raw exception text must not leak"


def test_missing_knowledge_base_is_reported_not_raised(service, monkeypatch, tmp_path):
    knowledge_base.load_kb.cache_clear()
    monkeypatch.setattr(knowledge_base.settings, "kb_path", tmp_path / "gone.json", raising=False)
    try:
        result = service.ask("my wifi is not connecting")
        # The tool converts the failure into a zero-confidence result, so the
        # agent escalates rather than crashing.
        assert result.ok
        assert result.escalated is True
    finally:
        knowledge_base.load_kb.cache_clear()


# --- Ollama availability -------------------------------------------------


def test_falls_back_when_ollama_is_unavailable(temp_db, monkeypatch):
    """With Ollama down, get_reasoner must hand back the rule-based reasoner."""
    monkeypatch.setattr(database.settings, "db_path", temp_db, raising=False)

    class Broken:
        def __init__(self, *args, **kwargs):
            raise ConnectionError("connection refused")

    monkeypatch.setattr(llm, "OllamaReasoner", Broken)
    llm.get_reasoner.cache_clear()
    try:
        service = HelpdeskService(force_offline=False)
        assert service.is_offline is True
        assert service.ask("my wifi is not connecting").ok
    finally:
        llm.get_reasoner.cache_clear()


def test_offline_mode_never_claims_an_llm_was_used(service):
    result = service.ask("my wifi is not connecting")
    assert "ollama" not in result.llm_mode.lower()


# --- tickets -------------------------------------------------------------


def test_ticket_status_transitions(service):
    service.ask("my quantum flux capacitor is misaligned")
    ticket = service.tickets()[0]
    assert ticket.status == "open"

    changed, message = service.set_ticket_status(ticket.ticket_id, "in_progress")
    assert changed and "in_progress" in message
    assert service.tickets()[0].status == "in_progress"

    changed, _ = service.set_ticket_status(ticket.ticket_id, "resolved")
    assert changed
    assert service.tickets(status="resolved")[0].ticket_id == ticket.ticket_id


def test_invalid_ticket_status_is_refused(service):
    service.ask("my quantum flux capacitor is misaligned")
    ticket = service.tickets()[0]
    changed, message = service.set_ticket_status(ticket.ticket_id, "banana")
    assert changed is False
    assert "not a valid status" in message


def test_updating_an_unknown_ticket_reports_clearly(service):
    changed, message = service.set_ticket_status("TKT-does-not-exist", "closed")
    assert changed is False
    assert "No ticket found" in message


def test_ticket_filtering_by_status(service):
    service.ask("my quantum flux capacitor is misaligned")
    service.ask("the flux inverter has decohered")
    assert len(service.tickets(status="open")) == 2
    assert service.tickets(status="closed") == []


# --- history and dashboard ----------------------------------------------


def test_history_records_the_routing_decision(service):
    service.ask("my wifi is not connecting")
    rows = service.history()
    assert len(rows) == 1
    assert rows[0]["tool_name"]
    assert rows[0]["route_reason"]
    assert rows[0]["created_at"].endswith("+00:00")


def test_history_is_newest_first(service):
    service.ask("my wifi is not connecting")
    service.ask("the printer is offline")
    rows = service.history()
    assert rows[0]["id"] > rows[1]["id"]


def test_dashboard_counters(service):
    service.ask("my wifi is not connecting")
    service.ask("my quantum flux capacitor is misaligned")
    board = service.dashboard()
    assert board.kb_articles == 16
    assert board.kb_categories == 12
    assert board.conversations == 2
    assert board.escalations == 1
    assert board.open_tickets == 1
    assert board.escalation_rate == pytest.approx(0.5)
    assert board.llm_mode == "Offline fallback mode"
    assert board.ollama_online is False


def test_dashboard_survives_a_broken_database(service, monkeypatch):
    monkeypatch.setattr(
        "helpdesk.service.database.stats",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk gone")),
    )
    board = service.dashboard()
    assert board.warnings and "Database unreadable" in board.warnings[0]


# --- health --------------------------------------------------------------


def test_health_reports_every_subsystem(service):
    names = {check.name for check in service.health()}
    assert {
        "Python environment",
        "Knowledge base",
        "SQLite database",
        "Ollama",
        "Reasoning mode",
    } <= names


def test_health_marks_offline_mode_as_a_warning_not_a_failure(service):
    checks = {check.name: check for check in service.health()}
    assert checks["Reasoning mode"].status == "warn"
    assert checks["Python environment"].status == "ok"
    assert all(check.status != "fail" for check in checks.values())


def test_health_flags_a_missing_knowledge_base(service, monkeypatch, tmp_path):
    knowledge_base.load_kb.cache_clear()
    monkeypatch.setattr(knowledge_base.settings, "kb_path", tmp_path / "gone.json", raising=False)
    try:
        checks = {check.name: check for check in service.health()}
        assert checks["Knowledge base"].status == "fail"
    finally:
        knowledge_base.load_kb.cache_clear()


# --- knowledge base browsing ---------------------------------------------


def test_kb_browse_returns_everything_by_default(service):
    assert len(service.kb_articles()) == 16


def test_kb_browse_filters_by_category(service):
    articles = service.kb_articles(category="vpn")
    assert articles
    assert {article.category for article in articles} == {"vpn"}


def test_kb_browse_all_category_is_not_a_filter(service):
    assert len(service.kb_articles(category="All")) == 16


def test_kb_browse_searches_text(service):
    articles = service.kb_articles(search="spooler")
    assert articles
    assert any("printer" in article.category for article in articles)


def test_kb_browse_unmatched_search_is_empty(service):
    assert service.kb_articles(search="zzzqqq") == []


def test_kb_categories_are_listed(service):
    categories = service.kb_categories()
    assert "vpn" in categories and "printer" in categories
    assert categories == sorted(categories)
