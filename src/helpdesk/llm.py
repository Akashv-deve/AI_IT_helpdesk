"""Reasoning layer.

Two interchangeable implementations of the same tiny interface:

``OllamaReasoner``
    The real thing — a local ``qwen2.5:3b`` model does the routing decision and
    writes the final answer.

``RuleBasedReasoner``
    A deterministic fallback used when Ollama isn't installed or running. It
    keeps the project runnable (and the test suite green) on any machine, which
    matters when someone clones the repo and wants to see it work immediately.

The agent graph never checks which one it holds; it just calls ``route()`` and
``synthesize()``. That is the whole point of putting an interface here.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from functools import lru_cache

from .config import settings
from .tools import DEFAULT_TOOL, TOOLS, ToolResult, tool_catalogue

ROUTER_PROMPT = """You are the routing component of an IT helpdesk agent.
Pick the single most appropriate tool for the user's problem.

Available tools:
{catalogue}

Respond with ONLY a JSON object, no prose and no markdown fences:
{{"tool": "<tool_name>", "reason": "<one short sentence>"}}

User problem: {query}
"""

SYNTHESIS_PROMPT = """You are a friendly IT support agent talking to a non-technical colleague.

Their problem: {query}

Reference material retrieved for you:
{tool_result}

Write the reply to send them. Rules:
- Open with one sentence naming the likely cause.
- Then give numbered steps, simplest and most likely fix first.
- Keep it under 200 words and skip anything they did not ask about.
- Never mention tools, JSON, confidence scores, or that you retrieved anything.
- If a ticket ID appears above, state it clearly and tell them to keep it.
"""

# Keyword triggers for the offline router, checked in priority order.
_ESCALATION_HINTS = (
    "ticket", "escalate", "raise a", "human", "technician", "nothing worked",
    "nothing works", "still not", "tried everything", "speak to someone",
    "log a call", "someone to look",
)
_SYSTEM_INFO_HINTS = (
    "system info", "system information", "my specs", "what os", "which os",
    "operating system", "hostname", "python version", "machine details",
)
_DIAGNOSIS_HINTS = (
    "why", "diagnose", "keeps", "randomly", "sometimes", "intermittent",
    "on and off", "what is causing", "what's causing", "root cause",
)


class LLMUnavailableError(RuntimeError):
    """Raised when Ollama cannot be reached or the model is not pulled."""


class Reasoner(ABC):
    """The interface the agent graph depends on."""

    mode: str = "unknown"

    @abstractmethod
    def route(self, query: str) -> tuple[str, str]:
        """Return ``(tool_name, human-readable reason)``."""

    @abstractmethod
    def synthesize(self, query: str, result: ToolResult) -> str:
        """Turn a tool result into the message shown to the user."""


# ---------------------------------------------------------------------------
# Offline / deterministic
# ---------------------------------------------------------------------------


class RuleBasedReasoner(Reasoner):
    """Keyword routing and template answers. No model, no network, no latency."""

    mode = "offline (rule-based)"

    def route(self, query: str) -> tuple[str, str]:
        lowered = query.lower()
        for hint in _ESCALATION_HINTS:
            if hint in lowered:
                return "create_support_ticket", f"the request mentions {hint!r}"
        for hint in _SYSTEM_INFO_HINTS:
            if hint in lowered:
                return "get_system_info", f"the request asks about {hint!r}"
        for hint in _DIAGNOSIS_HINTS:
            if hint in lowered:
                return "diagnose_issue", f"the wording {hint!r} suggests an open-ended symptom"
        return DEFAULT_TOOL, "defaulting to a knowledge-base lookup"

    def synthesize(self, query: str, result: ToolResult) -> str:
        if not result.ok:
            return (
                f"I ran into a problem handling that request.\n\n{result.text}\n\n"
                "Please try again, or ask me to raise a support ticket."
            )
        titles = result.metadata.get("matched_titles") or []
        if result.metadata.get("ticket_id") and not titles:
            opening = "I could not match this to anything in the knowledge base."
        elif titles:
            opening = f"This looks like **{titles[0]}**. Here is what usually fixes it:"
        else:
            opening = "Here is what I found:"
        closing = (
            "\n\nIf none of that helps, say *\"create a ticket\"* and I'll escalate "
            "it to the IT team."
        )
        return f"{opening}\n\n{result.text}{closing}"


# ---------------------------------------------------------------------------
# Ollama-backed
# ---------------------------------------------------------------------------


class OllamaReasoner(Reasoner):
    """Routes and writes with a local Ollama model."""

    def __init__(self, model: str | None = None) -> None:
        from langchain_ollama import ChatOllama  # imported lazily: it is slow

        self.model_name = model or settings.ollama_model
        self.mode = f"ollama ({self.model_name})"
        self._llm = ChatOllama(
            model=self.model_name,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
            num_predict=settings.llm_max_tokens,
        )
        self._fallback = RuleBasedReasoner()

    def _complete(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage

        response = self._llm.invoke([HumanMessage(content=prompt)])
        content = response.content
        if isinstance(content, list):  # some backends return content blocks
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return str(content).strip()

    def probe(self) -> None:
        """Raise :class:`LLMUnavailableError` unless the model answers."""
        try:
            self._complete("Reply with the single word: ok")
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

    def route(self, query: str) -> tuple[str, str]:
        try:
            raw = self._complete(ROUTER_PROMPT.format(catalogue=tool_catalogue(), query=query))
            payload = _extract_json(raw)
            tool = str(payload.get("tool", "")).strip()
            reason = str(payload.get("reason", "")).strip()
            if tool not in TOOLS:
                fallback_tool, fallback_reason = self._fallback.route(query)
                return fallback_tool, f"model picked an unknown tool; {fallback_reason}"
            return tool, reason or "selected by the routing model"
        except Exception as exc:
            tool, reason = self._fallback.route(query)
            return tool, f"routing model unavailable ({exc}); {reason}"

    def synthesize(self, query: str, result: ToolResult) -> str:
        try:
            answer = self._complete(
                SYNTHESIS_PROMPT.format(query=query, tool_result=result.text)
            )
            return answer or self._fallback.synthesize(query, result)
        except Exception:
            return self._fallback.synthesize(query, result)


# ---------------------------------------------------------------------------
# JSON extraction + factory
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of a model reply that may be wrapped in prose.

    Small models frequently answer with markdown fences or a sentence of
    preamble, so parsing has to survive both.
    """
    fenced = _FENCE_RE.search(text)
    candidate = fenced.group(1) if fenced else text
    match = _OBJECT_RE.search(candidate)
    if not match:
        raise ValueError(f"no JSON object in model reply: {text[:120]!r}")
    return json.loads(match.group(0))


@lru_cache(maxsize=2)
def get_reasoner(force_offline: bool = False) -> Reasoner:
    """Return the best available reasoner, cached for the process lifetime.

    Caching matters: the previous version rebuilt the client and sent a health
    -check prompt on *every* graph node, which tripled the latency of each turn.
    """
    if force_offline or settings.offline_forced:
        return RuleBasedReasoner()
    try:
        reasoner = OllamaReasoner()
        reasoner.probe()
        return reasoner
    except Exception:
        return RuleBasedReasoner()


def ollama_status() -> tuple[bool, str]:
    """Check Ollama for the ``doctor`` command. Returns ``(healthy, detail)``."""
    try:
        reasoner = OllamaReasoner()
        reasoner.probe()
        return True, f"{settings.ollama_model} responded at {settings.ollama_base_url}"
    except LLMUnavailableError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
