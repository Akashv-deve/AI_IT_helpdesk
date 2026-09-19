"""Streamlit front end for the AI IT Helpdesk.

This package contains presentation code only. Every question, ticket update and
status check goes through :class:`helpdesk.service.HelpdeskService`, so the
agent behaves identically whether it is driven from the browser or the terminal.
"""

__all__ = ["runner"]
