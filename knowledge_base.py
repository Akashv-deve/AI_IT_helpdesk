"""Local IT knowledge base loader and search."""

import json
import os
from typing import List, Dict, Any

KB_PATH = os.path.join(os.path.dirname(__file__), "data", "helpdesk_kb.json")


def load_kb() -> List[Dict[str, Any]]:
    if not os.path.exists(KB_PATH):
        raise FileNotFoundError(f"Knowledge base not found at {KB_PATH}")
    with open(KB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def search_knowledge_base(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Simple keyword-based search over the knowledge base.
    Returns the most relevant entries.
    """
    kb = load_kb()
    query_lower = query.lower()
    scored = []

    for entry in kb:
        score = 0
        # Title match
        if any(w in entry["title"].lower() for w in query_lower.split()):
            score += 3
        # Category match
        if entry["category"] in query_lower:
            score += 4
        # Symptom match
        for symptom in entry.get("symptoms", []):
            if symptom in query_lower or any(w in symptom for w in query_lower.split() if len(w) > 3):
                score += 2
        # Cause / step keyword boost
        text = " ".join(entry.get("causes", []) + entry.get("steps", [])).lower()
        for w in query_lower.split():
            if len(w) > 3 and w in text:
                score += 1

        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [e for _, e in scored[:top_k]]

    # Fallback: return a general entry if nothing matched
    if not results:
        results = [kb[0]]  # first entry as soft fallback

    return results


def format_kb_results(results: List[Dict[str, Any]]) -> str:
    """Format search results into readable text for the LLM."""
    if not results:
        return "No relevant knowledge base entries found."

    parts = []
    for i, entry in enumerate(results, 1):
        steps = "\n".join(f"  {j}. {s}" for j, s in enumerate(entry.get("steps", []), 1))
        causes = ", ".join(entry.get("causes", []))
        parts.append(
            f"[{i}] {entry['title']} (category: {entry['category']})\n"
            f"Possible causes: {causes}\n"
            f"Troubleshooting steps:\n{steps}"
        )
    return "\n\n".join(parts)
