"""Retrieval behaviour — the part that decides whether the agent is trustworthy."""

from __future__ import annotations

import pytest

from helpdesk.knowledge_base import (
    KnowledgeBaseError,
    categories,
    format_hits,
    load_kb,
    score_entry,
    search,
    tokenize,
)


def test_kb_loads_and_is_well_formed():
    entries = load_kb()
    assert len(entries) >= 10
    assert all(entry.title and entry.category for entry in entries)
    assert all(entry.steps for entry in entries), "every entry needs actionable steps"


def test_kb_ids_are_unique():
    ids = [entry.id for entry in load_kb()]
    assert len(ids) == len(set(ids))


def test_tokenize_removes_noise_words():
    tokens = tokenize("My printer is not working and I cannot print")
    assert "printer" in tokens
    assert "print" in tokens
    assert "not" not in tokens
    assert "and" not in tokens
    assert "my" not in tokens


@pytest.mark.parametrize(
    "query,expected_category",
    [
        ("my wifi is not connecting", "wifi"),
        ("the printer is offline and will not print", "printer"),
        ("vpn keeps disconnecting", "vpn"),
        ("i forgot my password", "password"),
    ],
)
def test_search_finds_the_right_category(query, expected_category):
    hits = search(query, top_k=3)
    assert hits, f"expected a match for {query!r}"
    assert expected_category in {hit.entry.category for hit in hits}


def test_search_returns_empty_rather_than_a_wrong_answer():
    """A miss must be a miss — the agent escalates on emptiness."""
    assert search("quantum flux capacitor misalignment banana", top_k=3) == []


def test_weak_matches_are_filtered_out():
    """A strong answer must not be diluted by barely-relevant filler."""
    hits = search("i forgot my password", top_k=3)
    assert hits[0].entry.category == "password"
    floor = hits[0].confidence * 0.5
    assert all(hit.confidence >= floor for hit in hits)
    assert "wifi" not in {hit.entry.category for hit in hits}


def test_confidence_is_bounded_and_ordered():
    hits = search("wifi not connecting", top_k=5)
    confidences = [hit.confidence for hit in hits]
    assert all(0.0 <= value <= 1.0 for value in confidences)
    assert confidences == sorted(confidences, reverse=True)


def test_relevant_query_scores_higher_than_irrelevant_one():
    entry = next(e for e in load_kb() if e.category == "printer")
    relevant = score_entry(tokenize("printer offline not printing"), entry)
    irrelevant = score_entry(tokenize("password reset email"), entry)
    assert relevant > irrelevant


def test_empty_query_returns_nothing():
    assert search("   ") == []
    assert search("a an the") == []


def test_format_hits_handles_empty_input():
    assert "No relevant" in format_hits([])


def test_format_hits_includes_steps():
    rendered = format_hits(search("wifi not connecting", top_k=1))
    assert "Troubleshooting steps" in rendered
    assert "1." in rendered


def test_categories_are_sorted_and_unique():
    result = categories()
    assert result == sorted(set(result))


def test_missing_kb_raises_a_helpful_error(tmp_path):
    with pytest.raises(KnowledgeBaseError, match="not found"):
        load_kb(tmp_path / "does_not_exist.json")
