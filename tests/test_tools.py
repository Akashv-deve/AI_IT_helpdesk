"""The four tools, plus the escalation rule built on top of them."""

from __future__ import annotations

from helpdesk import tools
from helpdesk.tools import ToolResult


def test_registry_matches_the_specs():
    assert set(tools.TOOLS) == {spec.name for spec in tools.TOOL_SPECS}
    assert tools.DEFAULT_TOOL in tools.TOOLS


def test_catalogue_lists_every_tool():
    catalogue = tools.tool_catalogue()
    for name in tools.TOOLS:
        assert name in catalogue


def test_search_tool_returns_confidence():
    result = tools.search_knowledge_base("my wifi will not connect")
    assert result.ok
    assert result.confidence > 0
    assert "Troubleshooting steps" in result.text


def test_search_tool_reports_a_miss_without_inventing():
    result = tools.search_knowledge_base("zzzz qqqq vvvv")
    assert result.confidence == 0.0
    assert "No relevant" in result.text


def test_diagnose_lists_causes_before_steps():
    result = tools.diagnose_issue("computer is extremely slow and freezes")
    assert "Probable causes" in result.text
    assert result.text.index("Probable causes") < result.text.index("Recommended steps")


def test_system_info_is_always_confident():
    result = tools.get_system_info()
    assert result.ok and result.confidence == 1.0
    assert "python_version" in result.text


def test_create_ticket_tool_exposes_the_id(temp_db, monkeypatch):
    monkeypatch.setattr(tools.database.settings, "db_path", temp_db, raising=False)
    result = tools.create_support_ticket("printer broken", "smoke coming out")
    assert result.ok
    assert result.metadata["ticket_id"].startswith("TKT-")
    assert result.metadata["ticket_id"] in result.text


def test_run_tool_dispatches_by_name():
    assert tools.run_tool("get_system_info").ok


def test_run_tool_rejects_unknown_names():
    result = tools.run_tool("definitely_not_a_tool")
    assert result.ok is False
    assert "Unknown tool" in result.text


def test_run_tool_survives_bad_arguments():
    result = tools.run_tool("search_knowledge_base", {"wrong_kwarg": 1})
    assert result.ok is False
    assert "Bad arguments" in result.text


def test_escalation_triggers_on_low_confidence():
    assert tools.needs_escalation(ToolResult(text="", confidence=0.0))
    assert tools.needs_escalation(ToolResult(text="", confidence=0.9, ok=False))
    assert not tools.needs_escalation(ToolResult(text="", confidence=0.9))
