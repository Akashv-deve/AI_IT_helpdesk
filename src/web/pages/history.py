"""Conversation history — every turn the agent has handled, from SQLite."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from helpdesk.config import settings
from web import state, theme


def render() -> None:
    theme.inject_css()
    service = state.get_service()

    theme.page_header(
        "Conversation history",
        "Persistent memory. Every turn is written to SQLite with the tool that ran, "
        "how confident retrieval was, and whether the confidence gate escalated it.",
    )

    rows = service.history(limit=200)
    if not rows:
        st.info("No conversations recorded yet. Ask a question on the Helpdesk page.", icon="🗂️")
        return

    frame = pd.DataFrame(
        {
            "#": [row["id"] for row in rows],
            "Question": [row["user_query"] for row in rows],
            "Tool used": [row["tool_name"] or "—" for row in rows],
            "Confidence": [f"{(row['confidence'] or 0):.0%}" for row in rows],
            "Escalated": ["Yes" if row["escalated"] else "—" for row in rows],
            "Reasoning mode": [row["llm_mode"] or "—" for row in rows],
            "Recorded (UTC)": [row["created_at"] for row in rows],
        }
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)

    escalated = sum(1 for row in rows if row["escalated"])
    st.markdown(
        f'<p class="hd-subtle">{len(rows)} turns shown · {escalated} escalated · '
        f"the agent raises a ticket below {settings.escalation_threshold:.0%} "
        "retrieval confidence.</p>",
        unsafe_allow_html=True,
    )

    with st.expander("Inspect a single turn"):
        labels = {f"#{row['id']} — {row['user_query'][:60]}": row for row in rows}
        picked = st.selectbox("Turn", list(labels))
        row = labels[picked]
        st.markdown("**Question**")
        st.write(row["user_query"])
        st.markdown("**Why this tool was chosen**")
        st.write(row["route_reason"] or "—")
        st.markdown("**Tool output**")
        st.code(row["tool_result"] or "—", language=None)
        st.markdown("**Answer given to the user**")
        st.markdown(row["final_response"] or "—")
