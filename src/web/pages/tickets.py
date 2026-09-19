"""Ticket management — reads and writes the same SQLite tables the CLI uses."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from helpdesk.database import VALID_STATUSES
from web import state, theme

STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In progress",
    "resolved": "Resolved",
    "closed": "Closed",
}


def render() -> None:
    theme.inject_css()
    service = state.get_service()

    theme.page_header(
        "Tickets",
        "Every escalation the agent could not resolve. Stored in the same SQLite "
        "database the CLI reads, so `python main.py tickets` shows exactly this.",
    )

    choice = st.selectbox(
        "Filter by status",
        ["All", *VALID_STATUSES],
        format_func=lambda value: "All" if value == "All" else STATUS_LABELS.get(value, value),
    )
    status = None if choice == "All" else choice

    tickets = service.tickets(limit=200, status=status)

    if not tickets:
        st.info(
            "No tickets yet. Ask the helpdesk something it cannot answer — the agent "
            "will escalate and a ticket will appear here.",
            icon="🎫",
        )
        return

    counts = {value: 0 for value in VALID_STATUSES}
    for ticket in service.tickets(limit=1000):
        counts[ticket.status] = counts.get(ticket.status, 0) + 1

    columns = st.columns(len(VALID_STATUSES))
    for column, value in zip(columns, VALID_STATUSES, strict=False):
        column.metric(STATUS_LABELS[value], counts.get(value, 0))

    st.divider()

    frame = pd.DataFrame(
        {
            "Ticket ID": [ticket.ticket_id for ticket in tickets],
            "Status": [STATUS_LABELS.get(ticket.status, ticket.status) for ticket in tickets],
            "Problem": [ticket.user_query for ticket in tickets],
            "Created (UTC)": [ticket.created_at for ticket in tickets],
        }
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)

    st.subheader("Update a ticket")
    st.markdown(
        '<p class="hd-subtle">Open a ticket to read the full description the agent '
        "recorded, and move it through the workflow.</p>",
        unsafe_allow_html=True,
    )

    for ticket in tickets[:50]:
        problem = ticket.user_query
        summary = problem if len(problem) <= 70 else problem[:67] + "…"
        with st.expander(f"{ticket.ticket_id} — {summary}"):
            st.markdown(theme.status_pill(ticket.status), unsafe_allow_html=True)
            st.markdown("**Reported problem**")
            st.write(ticket.user_query)
            st.markdown("**Description recorded by the agent**")
            st.code(ticket.description or "—", language=None)
            st.caption(f"Created {ticket.created_at}")

            left, right = st.columns([3, 1])
            with left:
                new_status = st.selectbox(
                    "Move to",
                    VALID_STATUSES,
                    index=VALID_STATUSES.index(ticket.status),
                    format_func=lambda value: STATUS_LABELS.get(value, value),
                    key=f"status_{ticket.ticket_id}",
                )
            with right:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Update", key=f"update_{ticket.ticket_id}", use_container_width=True):
                    if new_status == ticket.status:
                        st.info("That ticket is already in this status.")
                    else:
                        changed, message = service.set_ticket_status(
                            ticket.ticket_id, new_status
                        )
                        if changed:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
