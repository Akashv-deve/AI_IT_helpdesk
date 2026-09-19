"""Knowledge-base loading and retrieval.

The knowledge base is a small JSON file of curated IT issues. Retrieval is a
transparent, explainable keyword-overlap scorer rather than an embedding
model: it has no extra dependencies, runs instantly, and — importantly for a
helpdesk — returns a calibrated ``confidence`` that the agent uses to decide
whether it actually knows the answer or should escalate to a human.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import settings

# Words that carry no diagnostic signal and would otherwise inflate scores.
STOPWORDS: frozenset[str] = frozenset(
    """
    a an and any are as at be been but by can cant cannot could did do does
    doesnt dont for from get got had has have help how i im in into is it its
    just keep me my no not of on or our out please so some that the their them
    then there these they this to try up us use very was we well what when
    where which while who why will with wont would you your
    """.split()  # noqa: SIM905 - a prose block reads better than 60 quoted strings
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Joins hyphenated words so "Wi-Fi" becomes one token instead of two that are
# both too short to survive filtering.
_INNER_HYPHEN_RE = re.compile(r"(?<=\w)-(?=\w)")

# Relative weight of each signal. They sum to 1.0 so scores land in [0, 1].
W_COVERAGE = 0.45  # how much of the user's query this entry explains
W_TITLE = 0.20
W_SYMPTOM = 0.15
W_CATEGORY = 0.20  # naming a category ("vpn", "printer") is a strong signal

# A result is only kept if it scores at least this fraction of the best match.
# Without it a "forgot my password" query trails a 22%-relevant Wi-Fi article
# into the answer, which pollutes both the LLM prompt and what the user reads.
RELATIVE_FLOOR = 0.5


def tokenize(text: str) -> set[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords and 1-2 char noise."""
    normalised = _INNER_HYPHEN_RE.sub("", text.lower())
    return {
        token
        for token in _TOKEN_RE.findall(normalised)
        if len(token) > 2 and token not in STOPWORDS
    }


@dataclass(frozen=True)
class KBEntry:
    """A single curated knowledge-base article."""

    id: int
    category: str
    title: str
    symptoms: list[str] = field(default_factory=list)
    causes: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> KBEntry:
        return cls(
            id=int(raw["id"]),
            category=str(raw["category"]),
            title=str(raw["title"]),
            symptoms=list(raw.get("symptoms", [])),
            causes=list(raw.get("causes", [])),
            steps=list(raw.get("steps", [])),
        )


@dataclass(frozen=True)
class SearchHit:
    """A knowledge-base entry together with how well it matched the query."""

    entry: KBEntry
    confidence: float


class KnowledgeBaseError(RuntimeError):
    """Raised when the knowledge base is missing or malformed."""


@lru_cache(maxsize=4)
def load_kb(path: Path | None = None) -> tuple[KBEntry, ...]:
    """Load and validate the knowledge base. Cached — the file is read once."""
    kb_path = Path(path) if path else settings.kb_path
    if not kb_path.exists():
        raise KnowledgeBaseError(
            f"Knowledge base not found at {kb_path}. "
            "Check KB_PATH in your .env, or restore data/helpdesk_kb.json."
        )
    try:
        raw = json.loads(kb_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise KnowledgeBaseError(f"{kb_path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, list) or not raw:
        raise KnowledgeBaseError(f"{kb_path} must contain a non-empty JSON array.")

    try:
        return tuple(KBEntry.from_dict(item) for item in raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise KnowledgeBaseError(f"Malformed entry in {kb_path}: {exc}") from exc


def score_entry(query_tokens: set[str], entry: KBEntry) -> float:
    """Score one entry against the query, in the range [0, 1].

    Four signals are combined:

    * coverage  — the fraction of the user's meaningful words this entry explains
    * title     — any overlap with the article title
    * symptom   — overlap with the curated symptom phrases (the strongest signal)
    * category  — the category name appearing in the query ("vpn", "printer", ...)
    """
    if not query_tokens:
        return 0.0

    title_tokens = tokenize(entry.title)
    symptom_tokens = tokenize(" ".join(entry.symptoms))
    body_tokens = tokenize(" ".join(entry.causes + entry.steps))
    category_tokens = tokenize(entry.category.replace("_", " "))

    all_tokens = title_tokens | symptom_tokens | body_tokens | category_tokens

    coverage = len(query_tokens & all_tokens) / len(query_tokens)
    title_hit = len(query_tokens & title_tokens) / len(title_tokens) if title_tokens else 0.0
    symptom_hit = 1.0 if query_tokens & symptom_tokens else 0.0
    category_hit = 1.0 if query_tokens & category_tokens else 0.0

    score = (
        W_COVERAGE * coverage
        + W_TITLE * min(title_hit * 1.5, 1.0)
        + W_SYMPTOM * symptom_hit
        + W_CATEGORY * category_hit
    )
    return round(min(score, 1.0), 3)


def search(query: str, top_k: int | None = None) -> list[SearchHit]:
    """Return the best-matching entries, highest confidence first.

    Two rules keep the results honest:

    * nothing matches -> an **empty list**, not the closest article. The agent
      relies on that emptiness to escalate instead of answering confidently
      wrong.
    * weak matches are dropped if they score below ``RELATIVE_FLOOR`` of the
      best hit, so a strong answer is never diluted by filler.
    """
    limit = top_k if top_k is not None else settings.kb_top_k
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    hits = [
        SearchHit(entry=entry, confidence=score)
        for entry in load_kb()
        if (score := score_entry(query_tokens, entry)) > 0
    ]
    if not hits:
        return []

    hits.sort(key=lambda hit: (hit.confidence, -hit.entry.id), reverse=True)

    # Keep only results that are competitive with the best one. Returning three
    # articles regardless of quality is worse than returning one good one.
    floor = hits[0].confidence * RELATIVE_FLOOR
    return [hit for hit in hits if hit.confidence >= floor][:limit]


def format_hits(hits: list[SearchHit]) -> str:
    """Render search results as plain text for the LLM and the CLI."""
    if not hits:
        return "No relevant knowledge base entries found."

    blocks = []
    for index, hit in enumerate(hits, start=1):
        entry = hit.entry
        steps = "\n".join(f"  {n}. {step}" for n, step in enumerate(entry.steps, start=1))
        causes = ", ".join(entry.causes) or "not recorded"
        blocks.append(
            f"[{index}] {entry.title}  (category: {entry.category}, "
            f"match: {hit.confidence:.0%})\n\n"
            f"Possible causes: {causes}\n\n"
            f"Troubleshooting steps:\n\n{steps}"
        )
    return "\n\n".join(blocks)


def categories() -> list[str]:
    """Distinct categories present in the knowledge base, sorted."""
    return sorted({entry.category for entry in load_kb()})
