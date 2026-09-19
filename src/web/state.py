"""Session state and service wiring.

Streamlit reruns the whole script on every interaction, so anything expensive
must be cached and anything conversational must live in ``st.session_state``.
Both concerns are centralised here rather than scattered across the pages.
"""

from __future__ import annotations

import streamlit as st

from helpdesk.config import settings
from helpdesk.service import HelpdeskService, TurnResult


@st.cache_resource(show_spinner=False)
def _build_service(force_offline: bool) -> HelpdeskService:
    """Build the service once per offline setting and reuse it.

    ``cache_resource`` is the right decorator here rather than ``cache_data``:
    the service holds a compiled LangGraph and a live model client, which must
    not be serialised or copied between reruns.
    """
    return HelpdeskService(force_offline=force_offline)


def get_service() -> HelpdeskService:
    """Return the service matching the current sidebar toggle."""
    return _build_service(force_offline=st.session_state.get("force_offline", False))


def init_state() -> None:
    """Populate session defaults exactly once per browser session."""
    st.session_state.setdefault("turns", [])
    st.session_state.setdefault("force_offline", settings.offline_forced)
    st.session_state.setdefault("pending_query", None)
    st.session_state.setdefault("show_agent_details", True)
    st.session_state.setdefault("mcp_check", None)


def turns() -> list[TurnResult]:
    """The conversation for this browser session."""
    return st.session_state["turns"]


def record_turn(result: TurnResult) -> None:
    st.session_state["turns"].append(result)


def clear_turns() -> None:
    st.session_state["turns"] = []


def queue_query(text: str) -> None:
    """Stage a query (from an example button) for the next rerun."""
    st.session_state["pending_query"] = text


def take_pending_query() -> str | None:
    """Pop the staged query, if any."""
    pending = st.session_state.get("pending_query")
    st.session_state["pending_query"] = None
    return pending
