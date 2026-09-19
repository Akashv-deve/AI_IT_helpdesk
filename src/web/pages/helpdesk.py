"""Helpdesk chat page — the primary screen."""

from __future__ import annotations

import streamlit as st

from helpdesk.config import settings
from helpdesk.service import TurnResult
from web import state, theme

EXAMPLE_PROBLEMS = (
    "Wi-Fi keeps disconnecting",
    "Printer is offline",
    "VPN is not connecting",
    "Computer is very slow",
    "I forgot my password",
    "Email is not syncing",
    "Browser keeps crashing",
)

# Deliberately outside the knowledge base, to demonstrate escalation.
OUT_OF_SCOPE_EXAMPLE = "My quantum flux capacitor is misaligned"

TOOL_LABELS = {
    "search_knowledge_base": "Knowledge base search",
    "diagnose_issue": "Diagnostic analysis",
    "get_system_info": "System information",
    "create_support_ticket": "Ticket creation",
}


def _render_agent_details(result: TurnResult) -> None:
    """Show safe execution metadata — never hidden reasoning."""
    with st.expander("Agent details", expanded=False):
        left, right = st.columns(2)
        with left:
            st.markdown("**Tool selected**")
            st.write(TOOL_LABELS.get(result.tool_name, result.tool_name or "—"))
            st.markdown("**Routing reason**")
            st.write(result.route_reason or "—")
        with right:
            st.markdown("**Retrieval confidence**")
            tone = theme.confidence_tone(result.confidence, settings.escalation_threshold)
            st.markdown(
                theme.pill(f"{result.confidence:.0%}", tone)
                + f'<span class="hd-subtle"> · escalates below '
                f"{settings.escalation_threshold:.0%}</span>",
                unsafe_allow_html=True,
            )
            st.markdown("**Escalated to a human**")
            st.write("Yes" if result.escalated else "No")
            st.markdown("**Reasoning mode**")
            st.write(result.llm_mode or "—")
        st.caption(
            "These are execution facts recorded by the agent graph — which tool ran, "
            "how well retrieval matched, and whether the confidence gate fired."
        )


def _render_turn(result: TurnResult) -> None:
    with st.chat_message("user"):
        st.write(result.query or "—")

    with st.chat_message("assistant"):
        if not result.ok:
            st.warning(result.error)
            return

        if result.escalated and result.ticket_id:
            st.markdown(
                '<div class="hd-escalated">'
                "<strong>Escalated to the IT team.</strong><br>"
                '<span class="hd-subtle">Confidence was below the threshold, so the agent '
                "raised a ticket instead of guessing.</span><br>"
                f'<span class="hd-ticket-id">{result.ticket_id}</span>'
                "</div>",
                unsafe_allow_html=True,
            )
        elif result.ticket_id:
            st.markdown(
                '<div class="hd-escalated">'
                "<strong>Support ticket created.</strong><br>"
                f'<span class="hd-ticket-id">{result.ticket_id}</span>'
                "</div>",
                unsafe_allow_html=True,
            )

        st.markdown(result.answer or "_No response was produced._")

        if st.session_state.get("show_agent_details", True):
            _render_agent_details(result)


def _render_examples() -> None:
    st.markdown("**Common problems** — click one to try it:")
    columns = st.columns(4)
    for index, example in enumerate(EXAMPLE_PROBLEMS):
        with columns[index % 4]:
            if st.button(example, key=f"eg_{index}", use_container_width=True):
                state.queue_query(example)
                st.rerun()

    st.markdown(
        '<p class="hd-subtle">Or try something the knowledge base does not cover, '
        "to see the agent escalate rather than invent an answer:</p>",
        unsafe_allow_html=True,
    )
    if st.button(f"❓ {OUT_OF_SCOPE_EXAMPLE}", key="eg_oos", use_container_width=False):
        state.queue_query(OUT_OF_SCOPE_EXAMPLE)
        st.rerun()


def render() -> None:
    theme.inject_css()
    service = state.get_service()

    theme.page_header(
        "IT Helpdesk",
        "Describe a problem in plain English. The agent picks a tool, searches the "
        "knowledge base, and escalates to a human ticket when it is not confident.",
    )

    if service.is_offline:
        st.info(
            "**Offline fallback mode** — Ollama is not available, so routing and "
            "wording come from deterministic rules rather than a language model. "
            "Every other part of the agent works normally.",
            icon="⚙️",
        )

    conversation = state.turns()

    if not conversation:
        _render_examples()
        st.divider()
    else:
        with st.expander("Try another example problem", expanded=False):
            _render_examples()

    for result in conversation:
        _render_turn(result)

    typed = st.chat_input("Describe your IT problem…")
    query = state.take_pending_query() or typed

    if query is not None and not query.strip():
        # Whitespace-only submissions are a slip, not a question. Warn without
        # cluttering the transcript with an error bubble.
        st.warning("Please describe the problem before sending.")
    elif query:
        with st.spinner("Routing to a tool and searching the knowledge base…"):
            result = service.ask(query)
        state.record_turn(result)
        st.rerun()
