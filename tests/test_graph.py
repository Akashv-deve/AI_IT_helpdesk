"""The agent graph: routing, the conditional escalation branch, persistence."""

from __future__ import annotations

import pytest

from helpdesk import database, tools
from helpdesk.graph import answer_query, build_agent
from helpdesk.llm import Reasoner, RuleBasedReasoner, _extract_json
from helpdesk.tools import ToolResult


class ScriptedReasoner(Reasoner):
    """A reasoner that always picks a chosen tool, so routing is deterministic."""

    mode = "scripted"

    def __init__(self, tool_name: str):
        self.tool_name = tool_name

    def route(self, query: str) -> tuple[str, str]:
        return self.tool_name, "scripted for the test"

    def synthesize(self, query: str, result: ToolResult) -> str:
        return f"ANSWER: {result.text}"


@pytest.fixture(autouse=True)
def _isolate_db(temp_db, monkeypatch):
    monkeypatch.setattr(database.settings, "db_path", temp_db, raising=False)
    monkeypatch.setattr(tools.database.settings, "db_path", temp_db, raising=False)


def test_confident_query_answers_without_escalating(offline_reasoner):
    agent = build_agent(offline_reasoner)
    state = answer_query(agent, "my wifi is not connecting")
    assert state.get("escalated") is False
    assert state.get("confidence", 0.0) > 0
    assert state.get("answer")


def test_unmatched_query_escalates_and_raises_a_ticket(offline_reasoner):
    agent = build_agent(offline_reasoner)
    state = answer_query(agent, "my quantum flux capacitor is misaligned")
    assert state.get("escalated") is True
    assert str(state.get("ticket_id", "")).startswith("TKT-")
    assert len(database.list_tickets()) == 1


def test_escalated_result_bypasses_synthesis():
    agent = build_agent(ScriptedReasoner("search_knowledge_base"))
    # A low confidence query that triggers escalation
    state = answer_query(agent, "my quantum flux capacitor is misaligned")
    
    assert state.get("escalated") is True
    assert "ANSWER:" not in state.get("answer", "")  # Proves synthesis was entirely bypassed
    assert "I could not find a reliable knowledge-base match" in state.get("answer", "")
    assert state.get("ticket_id") is not None


def test_explicit_escalation_is_not_double_ticketed(offline_reasoner):
    agent = build_agent(offline_reasoner)
    state = answer_query(agent, "nothing worked, please raise a ticket")
    assert state.get("tool_name") == "create_support_ticket"
    assert len(database.list_tickets()) == 1, "must not create a second ticket"


def test_system_info_route(offline_reasoner):
    agent = build_agent(offline_reasoner)
    state = answer_query(agent, "show me my system information")
    assert state.get("tool_name") == "get_system_info"
    assert state.get("escalated") is False


def test_router_choice_is_respected():
    agent = build_agent(ScriptedReasoner("diagnose_issue"))
    state = answer_query(agent, "the printer is offline")
    assert state.get("tool_name") == "diagnose_issue"


def test_unknown_tool_falls_back_to_the_default():
    agent = build_agent(ScriptedReasoner("no_such_tool"))
    state = answer_query(agent, "my wifi is broken")
    assert state.get("tool_name") == tools.DEFAULT_TOOL


def test_every_turn_is_persisted(offline_reasoner):
    agent = build_agent(offline_reasoner)
    answer_query(agent, "my wifi is not connecting")
    answer_query(agent, "the printer is offline")
    assert database.stats()["conversations"] == 2


def test_persist_can_be_disabled(offline_reasoner):
    agent = build_agent(offline_reasoner)
    answer_query(agent, "my wifi is not connecting", persist=False)
    assert database.stats()["conversations"] == 0


def test_rule_based_router_keywords():
    reasoner = RuleBasedReasoner()
    assert reasoner.route("please raise a ticket")[0] == "create_support_ticket"
    assert reasoner.route("what os am i on")[0] == "get_system_info"
    assert reasoner.route("why does my laptop keeps freezing")[0] == "diagnose_issue"
    assert reasoner.route("printer offline")[0] == "search_knowledge_base"


@pytest.mark.parametrize(
    "raw",
    [
        '{"tool": "diagnose_issue", "reason": "vague symptoms"}',
        '```json\n{"tool": "diagnose_issue", "reason": "vague symptoms"}\n```',
        'Sure! Here you go:\n{"tool": "diagnose_issue", "reason": "vague symptoms"}\nDone.',
    ],
)
def test_json_extraction_survives_chatty_models(raw):
    assert _extract_json(raw)["tool"] == "diagnose_issue"


def test_json_extraction_reports_garbage():
    with pytest.raises(ValueError):
        _extract_json("I am afraid I cannot do that.")