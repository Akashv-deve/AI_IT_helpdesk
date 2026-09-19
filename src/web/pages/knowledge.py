"""Knowledge base browser — reads data/helpdesk_kb.json through the service."""

from __future__ import annotations

import streamlit as st

from web import state, theme


def render() -> None:
    theme.inject_css()
    service = state.get_service()

    theme.page_header(
        "Knowledge base",
        "The curated articles the agent retrieves from. Anything outside this set "
        "scores zero and is escalated rather than answered.",
    )

    categories = service.kb_categories()
    if not categories:
        st.error(
            "The knowledge base could not be read. Check that data/helpdesk_kb.json "
            "exists and contains valid JSON, or run the Diagnostics page.",
            icon="⚠️",
        )
        return

    left, right = st.columns([1, 2])
    with left:
        category = st.selectbox(
            "Category",
            ["All", *categories],
            format_func=lambda value: value.replace("_", " ").title(),
        )
    with right:
        search = st.text_input("Search", placeholder="e.g. driver, password, spooler")

    articles = service.kb_articles(category=category, search=search)

    st.markdown(
        f'<p class="hd-subtle">{len(articles)} article'
        f"{'' if len(articles) == 1 else 's'} matching.</p>",
        unsafe_allow_html=True,
    )

    if not articles:
        st.info("Nothing matched those filters. Try a broader search term.", icon="🔍")
        return

    for article in articles:
        with st.expander(f"{article.title}  ·  {article.category.replace('_', ' ')}"):
            if article.symptoms:
                st.markdown("**Symptoms users report**")
                st.markdown("\n".join(f"- {item}" for item in article.symptoms))
            if article.causes:
                st.markdown("**Probable causes**")
                st.markdown("\n".join(f"- {item}" for item in article.causes))
            if article.steps:
                st.markdown("**Troubleshooting steps**")
                st.markdown(
                    "\n".join(f"{n}. {step}" for n, step in enumerate(article.steps, start=1))
                )
