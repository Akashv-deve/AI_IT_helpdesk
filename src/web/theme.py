"""Styling and small presentational helpers.

Deliberately restrained: this should read as an internal IT tool, not a landing
page. A handful of CSS rules, a status pill, and consistent colours for the
three states the app can be in.
"""

from __future__ import annotations

import streamlit as st

# Semantic colours reused by pills, metrics and the diagnostics table.
COLOURS = {
    "ok": "#1a7f37",
    "warn": "#9a6700",
    "fail": "#b42318",
    "info": "#0b5cad",
    "muted": "#57606a",
}

STATUS_COLOURS = {
    "open": "#b42318",
    "in_progress": "#9a6700",
    "resolved": "#1a7f37",
    "closed": "#57606a",
}

_CSS = """
<style>
  /* Tighten the default Streamlit padding so the app feels like a tool. */
  .block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1100px; }

  .hd-pill {
    display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px;
    font-size: 0.78rem; font-weight: 600; letter-spacing: 0.01em;
    border: 1px solid currentColor; white-space: nowrap;
  }
  .hd-subtle { color: #57606a; font-size: 0.86rem; }

  .hd-card {
    border: 1px solid rgba(128,128,128,0.25); border-radius: 10px;
    padding: 0.9rem 1.1rem; margin-bottom: 0.75rem;
  }
  .hd-card h4 { margin: 0 0 0.35rem 0; font-size: 0.95rem; }

  .hd-escalated {
    border-left: 4px solid #9a6700; background: rgba(154,103,0,0.07);
    padding: 0.75rem 1rem; border-radius: 6px; margin: 0.4rem 0 0.2rem 0;
  }
  .hd-ticket-id {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 1.02rem; font-weight: 700; letter-spacing: 0.02em;
  }
  /* Keep long tables readable rather than clipped. */
  [data-testid="stDataFrame"] { border-radius: 8px; }
</style>
"""


def inject_css() -> None:
    """Apply the stylesheet once per page render."""
    st.markdown(_CSS, unsafe_allow_html=True)


def pill(label: str, tone: str = "info") -> str:
    """Return an inline status pill as HTML."""
    colour = COLOURS.get(tone, COLOURS["info"])
    return f'<span class="hd-pill" style="color:{colour}">{label}</span>'


def status_pill(status: str) -> str:
    """Return a coloured pill for a ticket status."""
    colour = STATUS_COLOURS.get(status, COLOURS["muted"])
    label = status.replace("_", " ")
    return f'<span class="hd-pill" style="color:{colour}">{label}</span>'


def confidence_tone(confidence: float, threshold: float) -> str:
    """Map a retrieval confidence onto a semantic colour."""
    if confidence < threshold:
        return "fail"
    if confidence < threshold * 2:
        return "warn"
    return "ok"


def page_header(title: str, subtitle: str = "") -> None:
    """Consistent page title block."""
    st.title(title)
    if subtitle:
        st.markdown(f'<p class="hd-subtle">{subtitle}</p>', unsafe_allow_html=True)
