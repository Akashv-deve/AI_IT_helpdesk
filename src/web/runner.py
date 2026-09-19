"""Application shell: page configuration, sidebar and navigation."""

from __future__ import annotations

import streamlit as st

from helpdesk import __version__
from helpdesk.config import settings
from web import state, theme
from web.pages import dashboard, diagnostics, helpdesk, history, knowledge, tickets


def _sidebar() -> None:
    service = state.get_service()
    with st.sidebar:
        st.markdown("### AI IT Helpdesk")
        st.markdown(
            f'<p class="hd-subtle">v{__version__} · runs entirely on this machine</p>',
            unsafe_allow_html=True,
        )

        if service.is_offline:
            st.markdown(theme.pill("Offline fallback mode", "warn"), unsafe_allow_html=True)
        else:
            st.markdown(theme.pill("Ollama AI mode", "ok"), unsafe_allow_html=True)
        st.caption(service.llm_mode)

        st.divider()
        st.toggle(
            "Force offline mode",
            key="force_offline",
            help=(
                "Skip Ollama and use the deterministic rule-based reasoner. "
                "Useful for a fast, reproducible demo."
            ),
        )
        st.toggle(
            "Show agent details",
            key="show_agent_details",
            help="Expandable execution metadata under each answer.",
        )

        st.divider()
        if st.button("Clear this conversation", use_container_width=True):
            state.clear_turns()
            st.rerun()

        st.caption(
            f"Model: {settings.ollama_model}  \n"
            f"Escalates below {settings.escalation_threshold:.0%} confidence"
        )


def run() -> None:
    """Entry point called by ``app.py``."""
    st.set_page_config(
        page_title="AI IT Helpdesk",
        page_icon="🛠️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    theme.inject_css()
    state.init_state()
    _sidebar()

    # Every page function is called `render`, so Streamlit would infer the same
    # URL pathname for all of them. url_path must be set explicitly.
    navigation = st.navigation(
        [
            st.Page(
                helpdesk.render, title="Helpdesk", icon="💬",
                url_path="helpdesk", default=True,
            ),
            st.Page(tickets.render, title="Tickets", icon="🎫", url_path="tickets"),
            st.Page(history.render, title="History", icon="🗂️", url_path="history"),
            st.Page(
                knowledge.render, title="Knowledge base", icon="📚", url_path="knowledge-base"
            ),
            st.Page(dashboard.render, title="Dashboard", icon="📊", url_path="dashboard"),
            st.Page(
                diagnostics.render, title="Diagnostics", icon="🩺", url_path="diagnostics"
            ),
        ]
    )
    navigation.run()
