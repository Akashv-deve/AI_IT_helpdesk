"""The four helpdesk tools — one definition, two consumers.

``mcp_server.py`` exposes these over the Model Context Protocol and
``graph.py`` calls them in-process. Both import from here, so a tool can never
drift between the two surfaces (a real bug in the first version of this
project, where the logic was copy-pasted into both files).

Each tool returns a :class:`ToolResult` carrying free text *plus* a confidence
score. The MCP layer flattens that to the text the protocol expects, while the
agent uses the confidence to decide whether to escalate.
"""

from __future__ import annotations

import platform
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import database
from .config import settings
from .knowledge_base import KnowledgeBaseError, format_hits, search


@dataclass(frozen=True)
class ToolResult:
    """What a tool returns: text for the user, plus metadata for the agent."""

    text: str
    confidence: float = 0.0
    ok: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSpec:
    """Everything needed to advertise a tool to the router and to MCP."""

    name: str
    description: str
    func: Callable[..., ToolResult]
    arg_name: str | None  # the primary argument the router must fill in


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def search_knowledge_base(query: str) -> ToolResult:
    """Look up troubleshooting steps for a common IT problem."""
    try:
        hits = search(query)
    except KnowledgeBaseError as exc:
        return ToolResult(text=f"Knowledge base unavailable: {exc}", confidence=0.0, ok=False)

    if not hits:
        return ToolResult(
            text=(
                "No relevant knowledge base entries found for that description. "
                "More detail about the exact error message would help."
            ),
            confidence=0.0,
        )

    return ToolResult(
        text=format_hits(hits),
        confidence=hits[0].confidence,
        metadata={"matched_titles": [hit.entry.title for hit in hits]},
    )


def diagnose_issue(problem_description: str) -> ToolResult:
    """Analyse a problem and lay out likely causes before the fix steps."""
    try:
        hits = search(problem_description, top_k=2)
    except KnowledgeBaseError as exc:
        return ToolResult(text=f"Knowledge base unavailable: {exc}", confidence=0.0, ok=False)

    if not hits:
        return ToolResult(
            text=(
                "Unable to diagnose this precisely. Please describe the symptoms, "
                "any error message shown, and when the problem started."
            ),
            confidence=0.0,
        )

    lines = ["Diagnostic summary based on the reported symptoms:", ""]
    for hit in hits:
        entry = hit.entry
        lines.append(f"Likely issue: {entry.title}  (match: {hit.confidence:.0%})")
        lines.append("")
        lines.append("Probable causes:")
        lines.extend(f"  - {cause}" for cause in entry.causes)
        lines.append("")
        lines.append("Recommended steps:")
        lines.extend(f"  {n}. {step}" for n, step in enumerate(entry.steps, start=1))
        lines.append("")

    return ToolResult(
        text="\n".join(lines).rstrip(),
        confidence=hits[0].confidence,
        metadata={"matched_titles": [hit.entry.title for hit in hits]},
    )


def get_system_info() -> ToolResult:
    """Report basic, non-sensitive information about the local machine."""
    info = {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor() or "N/A",
        "hostname": socket.gethostname(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }
    body = "\n".join(f"{key}: {value}" for key, value in info.items())
    # Deterministic and always correct, so confidence is maximal.
    return ToolResult(text=f"System information:\n{body}", confidence=1.0, metadata=info)


def create_support_ticket(user_query: str, description: str = "") -> ToolResult:
    """Escalate to a human by recording a ticket in SQLite."""
    try:
        ticket_id = database.create_ticket(user_query, description)
    except Exception as exc:  # sqlite errors, permissions, disk full...
        return ToolResult(
            text=f"Could not create a support ticket: {exc}", confidence=0.0, ok=False
        )

    return ToolResult(
        text=(
            f"Support ticket created.\n"
            f"Ticket ID: {ticket_id}\n"
            f"Status: open\n"
            f"Keep this ID when following up with the IT support team."
        ),
        confidence=1.0,
        metadata={"ticket_id": ticket_id},
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="search_knowledge_base",
        description=(
            "Look up troubleshooting steps for a common IT problem "
            "(Wi-Fi, printer, email, password, VPN, browser, slow computer)."
        ),
        func=search_knowledge_base,
        arg_name="query",
    ),
    ToolSpec(
        name="diagnose_issue",
        description=(
            "Analyse a problem in more depth and return probable causes "
            "alongside the fix, for vague or multi-symptom reports."
        ),
        func=diagnose_issue,
        arg_name="problem_description",
    ),
    ToolSpec(
        name="get_system_info",
        description="Report the local OS, hostname, architecture and Python version.",
        func=get_system_info,
        arg_name=None,
    ),
    ToolSpec(
        name="create_support_ticket",
        description=(
            "Raise a ticket for a human technician when the user asks to escalate "
            "or when self-service steps have already failed."
        ),
        func=create_support_ticket,
        arg_name="user_query",
    ),
)

TOOLS: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}
DEFAULT_TOOL = "search_knowledge_base"


def tool_catalogue() -> str:
    """Bulleted tool list injected into the router prompt."""
    return "\n".join(f"- {spec.name}: {spec.description}" for spec in TOOL_SPECS)


def run_tool(name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
    """Dispatch to a tool by name, converting any failure into a ToolResult."""
    spec = TOOLS.get(name)
    if spec is None:
        return ToolResult(
            text=f"Unknown tool {name!r}. Available tools: {', '.join(TOOLS)}.",
            confidence=0.0,
            ok=False,
        )
    try:
        return spec.func(**(arguments or {}))
    except TypeError as exc:
        return ToolResult(text=f"Bad arguments for {name}: {exc}", confidence=0.0, ok=False)
    except Exception as exc:  # a tool must never crash the agent loop
        return ToolResult(text=f"Tool {name} failed: {exc}", confidence=0.0, ok=False)


def needs_escalation(result: ToolResult) -> bool:
    """True when the tool result is too weak to hand back as an answer."""
    return result.ok is False or result.confidence < settings.escalation_threshold
