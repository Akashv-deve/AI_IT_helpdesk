"""Shared fixtures. Every test runs against a throwaway database."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from helpdesk import database  # noqa: E402
from helpdesk.llm import RuleBasedReasoner  # noqa: E402


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the app at an isolated SQLite file for the duration of a test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database.settings, "db_path", db_path, raising=False)
    database.init_db(db_path)
    return db_path


@pytest.fixture
def offline_reasoner():
    """The deterministic reasoner, so tests never need Ollama running."""
    return RuleBasedReasoner()
