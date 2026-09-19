"""Status dashboard — counters drawn from the live knowledge base and database."""

from __future__ import annotations

import streamlit as st

from helpdesk.config import settings
from web import state, theme


def render() -> None:
    theme.inject_css()
    service = state.get_service()
    board = service.dashboard()

    theme.page_header(
        "Dashboard",
        "A snapshot of what the helpdesk knows and what it has handled.",
    )

    for warning in board.warnings:
        st.warning(warning, icon="⚠️")

    row = st.columns(4)
    row[0].metric("Knowledge articles", board.kb_articles, f"{board.kb_categories} categories")
    row[1].metric("Conversations handled", board.conversations)
    row[2].metric(
        "Escalated to a human",
        board.escalations,
        f"{board.escalation_rate:.0%} of turns" if board.conversations else None,
    )
    row[3].metric("Open tickets", board.open_tickets, f"{board.total_tickets} total")

    st.divider()
    st.subheader("Application status")

    left, right = st.columns(2)
    with left:
        tone = "ok" if board.ollama_online else "warn"
        st.markdown("**Reasoning mode**")
        st.markdown(theme.pill(board.llm_mode, tone), unsafe_allow_html=True)
        st.markdown("**Configured model**")
        st.code(board.model, language=None)
        st.markdown("**Ollama endpoint**")
        st.code(settings.ollama_base_url, language=None)

    with right:
        st.markdown("**Application**")
        st.markdown(theme.pill("Running", "ok"), unsafe_allow_html=True)
        st.markdown("**Escalation threshold**")
        st.markdown(
            theme.pill(f"{settings.escalation_threshold:.0%} retrieval confidence", "info"),
            unsafe_allow_html=True,
        )
        st.markdown("**Data location**")
        st.code(str(settings.db_path), language=None)

    if not board.ollama_online:
        st.info(
            "Running on the deterministic fallback. Routing and wording come from "
            "keyword rules; retrieval, escalation, ticketing and persistence are "
            "unchanged. See the Diagnostics page to bring Ollama online.",
            icon="⚙️",
        )
