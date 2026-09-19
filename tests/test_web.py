"""Web UI tests driven through Streamlit's own AppTest harness.

These run the real script in-process and fail on any render-time exception, so
they catch the class of bug an HTTP status check cannot — a page that returns
200 but throws once Streamlit actually executes it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit", reason="Streamlit is not installed")

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from helpdesk import database, tools  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = str(REPO_ROOT / "app.py")
SRC_DIR = str(REPO_ROOT / "src")

PAGE_MODULES = ["helpdesk", "tickets", "history", "knowledge", "dashboard", "diagnostics"]

PAGE_SCRIPT = """
import sys
sys.path.insert(0, {src!r})
import streamlit as st
from web import state
state.init_state()
st.session_state["force_offline"] = True
from web.pages import {module} as page
page.render()
"""


@pytest.fixture(autouse=True)
def _isolate(temp_db, monkeypatch):
    """Point the UI at a throwaway database and drop cached services."""
    monkeypatch.setattr(database.settings, "db_path", temp_db, raising=False)
    monkeypatch.setattr(tools.database.settings, "db_path", temp_db, raising=False)
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _app() -> AppTest:
    app = AppTest.from_file(APP_FILE, default_timeout=120)
    app.session_state["force_offline"] = True
    app.run()
    return app


# --- application startup -------------------------------------------------


def test_app_starts_without_errors():
    app = _app()
    assert app.exception == []
    assert app.title[0].value == "IT Helpdesk"


def test_sidebar_offers_the_offline_and_details_toggles():
    app = _app()
    labels = {toggle.label for toggle in app.toggle}
    assert labels == {"Force offline mode", "Show agent details"}


def test_offline_mode_is_announced_not_hidden():
    app = _app()
    banners = " ".join(info.value for info in app.info)
    assert "Offline fallback mode" in banners


def test_example_problem_buttons_are_offered():
    app = _app()
    labels = [button.label for button in app.button]
    assert "Printer is offline" in labels
    assert any(label.startswith("❓") for label in labels)


def test_chat_input_is_present():
    assert len(_app().chat_input) == 1


# --- the UI-to-agent invocation layer ------------------------------------


def test_typed_question_is_answered():
    app = _app()
    app.chat_input[0].set_value("my wifi is not connecting").run()

    turns = app.session_state["turns"]
    assert len(turns) == 1
    assert turns[0].ok and turns[0].answer
    assert turns[0].escalated is False
    assert app.exception == []


def test_repeated_questions_accumulate_in_one_session():
    app = _app()
    app.chat_input[0].set_value("my wifi is not connecting").run()
    app.chat_input[0].set_value("the printer is offline").run()
    app.chat_input[0].set_value("i forgot my password").run()

    assert len(app.session_state["turns"]) == 3
    assert app.exception == []


def test_example_button_submits_a_query():
    app = _app()
    button = next(b for b in app.button if b.label == "Printer is offline")
    button.click().run()

    turns = app.session_state["turns"]
    assert len(turns) == 1
    assert turns[0].query == "Printer is offline"


def test_out_of_scope_question_escalates_and_shows_the_ticket():
    app = _app()
    button = next(b for b in app.button if b.label.startswith("❓"))
    button.click().run()

    turn = app.session_state["turns"][0]
    assert turn.escalated is True
    assert turn.ticket_id.startswith("TKT-")

    rendered = " ".join(block.value for block in app.markdown)
    assert turn.ticket_id in rendered, "the ticket ID must be visible to the user"
    assert "Escalated to the IT team" in rendered


def test_escalation_persists_a_ticket():
    app = _app()
    next(b for b in app.button if b.label.startswith("❓")).click().run()
    assert len(database.list_tickets()) == 1


def test_blank_input_warns_without_recording_a_turn():
    app = _app()
    app.chat_input[0].set_value("   ").run()

    assert app.session_state["turns"] == []
    assert any("describe the problem" in w.value.lower() for w in app.warning)
    assert app.exception == []


def test_clear_conversation_empties_the_session():
    app = _app()
    app.chat_input[0].set_value("my wifi is not connecting").run()
    assert len(app.session_state["turns"]) == 1

    next(b for b in app.button if b.label == "Clear this conversation").click().run()
    assert app.session_state["turns"] == []


def test_agent_details_can_be_switched_off():
    app = _app()
    app.session_state["show_agent_details"] = False
    app.chat_input[0].set_value("my wifi is not connecting").run()
    assert app.exception == []
    assert len(app.expander) == 1, "only the 'try another example' expander should remain"


# --- every page renders --------------------------------------------------


@pytest.mark.parametrize("module", PAGE_MODULES)
def test_page_renders_without_exception(module):
    app = AppTest.from_string(
        PAGE_SCRIPT.format(src=SRC_DIR, module=module), default_timeout=120
    )
    app.run()
    assert app.exception == [], f"{module} page raised: {[e.value for e in app.exception]}"


@pytest.mark.parametrize("module", PAGE_MODULES)
def test_page_renders_with_data_present(module):
    """Pages must handle populated tables, not just the empty state."""
    database.save_conversation(
        user_query="my wifi is not connecting",
        route_reason="keyword match",
        tool_name="search_knowledge_base",
        tool_result="steps",
        final_response="restart the router",
        confidence=0.8,
        escalated=True,
        llm_mode="offline (rule-based)",
    )
    database.create_ticket("my wifi is not connecting", "escalated automatically")

    app = AppTest.from_string(
        PAGE_SCRIPT.format(src=SRC_DIR, module=module), default_timeout=120
    )
    app.run()
    assert app.exception == [], f"{module} page raised: {[e.value for e in app.exception]}"


def test_dashboard_shows_live_counters():
    database.save_conversation(
        user_query="q", route_reason="r", tool_name="search_knowledge_base",
        tool_result="t", final_response="f", confidence=0.9, escalated=False,
    )
    app = AppTest.from_string(
        PAGE_SCRIPT.format(src=SRC_DIR, module="dashboard"), default_timeout=120
    )
    app.run()
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Knowledge articles"] == "16"
    assert metrics["Conversations handled"] == "1"


def test_diagnostics_lists_every_check():
    app = AppTest.from_string(
        PAGE_SCRIPT.format(src=SRC_DIR, module="diagnostics"), default_timeout=120
    )
    app.run()
    rendered = " ".join(block.value for block in app.markdown)
    for name in ("Python environment", "Knowledge base", "SQLite database", "Ollama"):
        assert name in rendered
