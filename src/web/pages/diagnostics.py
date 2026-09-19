"""Diagnostics — the same checks `python main.py doctor` runs, rendered in the browser."""

from __future__ import annotations

import streamlit as st

from helpdesk.config import settings
from web import state, theme

ICONS = {"ok": "✅", "warn": "⚠️", "fail": "❌"}


def _render_check(check) -> None:
    icon = ICONS.get(check.status, "•")
    st.markdown(
        f'<div class="hd-card"><h4>{icon} {check.name} &nbsp; '
        f"{theme.pill(check.status, check.status)}</h4>"
        f"{check.detail}"
        + (f'<br><span class="hd-subtle">{check.hint}</span>' if check.hint else "")
        + "</div>",
        unsafe_allow_html=True,
    )


def render() -> None:
    theme.inject_css()
    service = state.get_service()

    theme.page_header(
        "Diagnostics",
        "Environment and setup checks. Identical to `python main.py doctor` — both "
        "call the same service method.",
    )

    checks = service.health()
    for check in checks:
        _render_check(check)

    if any(check.status == "fail" for check in checks):
        st.error("At least one check failed. The app may not work correctly.", icon="❌")
    elif service.is_offline:
        st.warning(
            "The application is fully functional but running in **offline fallback "
            "mode** — no language model is involved in routing or wording.",
            icon="⚙️",
        )
    else:
        st.success("All checks passed. Running in Ollama AI mode.", icon="✅")

    st.divider()
    st.subheader("MCP server")
    st.markdown(
        '<p class="hd-subtle">The four tools are also exposed over the Model Context '
        "Protocol. This button spawns the server as a subprocess, completes the stdio "
        "handshake and lists what it advertises — the same thing "
        "<code>python main.py mcp-check</code> does from the terminal.</p>",
        unsafe_allow_html=True,
    )

    if st.button("Run MCP handshake"):
        with st.spinner("Starting the MCP server over stdio…"):
            st.session_state["mcp_check"] = service.mcp_health()

    result = st.session_state.get("mcp_check")
    if result is not None:
        _render_check(result)

    st.divider()
    st.subheader("Enable Ollama")
    st.markdown(
        f"""
1. Install Ollama from [ollama.com](https://ollama.com).
2. Pull the configured model:
   ```powershell
   ollama pull {settings.ollama_model}
   ```
3. Leave Ollama running, clear the **Force offline mode** toggle in the sidebar,
   and reload this page.

Model and endpoint are read from `.env` (`OLLAMA_MODEL`, `OLLAMA_BASE_URL`,
`LLM_TEMPERATURE`, `LLM_MAX_TOKENS`). Nothing is hard-coded and no query ever
leaves this machine.
"""
    )
