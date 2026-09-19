"""The LangGraph agent.

    route ──> execute ──┬──(confident)──────────────> respond ──> END
                        └──(weak match)──> escalate ─┘

The conditional edge is the part that makes this an agent rather than a
pipeline: after running a tool the graph inspects the retrieval confidence and
decides on its own whether to answer or to raise a ticket for a human. A
helpdesk that confidently invents an answer is worse than one that says "I
don't know, here's your ticket number."
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from . import database
from .config import settings
from .llm import Reasoner, get_reasoner
from .tools import DEFAULT_TOOL, TOOLS, ToolResult, needs_escalation, run_tool


class AgentState(TypedDict, total=False):
    """Everything that flows through the graph for one user turn."""

    query: str
    tool_name: str
    tool_args: dict[str, Any]
    route_reason: str
    tool_result: str
    tool_metadata: dict[str, Any]
    confidence: float
    escalated: bool
    ticket_id: str | None
    answer: str
    llm_mode: str


def _build_args(tool_name: str, query: str) -> dict[str, Any]:
    """Fill the tool's primary argument from the user's query."""
    spec = TOOLS.get(tool_name)
    if spec is None or spec.arg_name is None:
        return {}
    if tool_name == "create_support_ticket":
        return {"user_query": query, "description": query}
    return {spec.arg_name: query}


def _route_node(state: AgentState, reasoner: Reasoner) -> AgentState:
    """Decide which tool answers this query."""
    query = state.get("query", "")
    try:
        tool_name, reason = reasoner.route(query)
    except Exception as exc:
        tool_name, reason = DEFAULT_TOOL, f"router error, falling back ({exc})"
    if tool_name not in TOOLS:
        tool_name, reason = DEFAULT_TOOL, "unknown tool requested, falling back"
    return {
        "tool_name": tool_name,
        "route_reason": reason,
        "tool_args": _build_args(tool_name, query),
        "llm_mode": reasoner.mode,
    }


def _execute_node(state: AgentState) -> AgentState:
    """Run the selected tool."""
    result = run_tool(state.get("tool_name", ""), state.get("tool_args", {}))
    return {
        "tool_result": result.text,
        # Carried forward so the synthesis node can name the matched article.
        # Dropping it here made every offline answer open with the generic
        # "Here is what I found" instead of "This looks like <issue>".
        "tool_metadata": dict(result.metadata),
        "confidence": result.confidence,
        "ticket_id": result.metadata.get("ticket_id"),
        "_ok": result.ok,  # type: ignore[typeddict-unknown-key]
    }


def _should_escalate(state: AgentState) -> str:
    """Conditional edge: answer directly, or raise a ticket first."""
    if state.get("tool_name") == "create_support_ticket":
        return "respond"  # already escalated by the router
    probe = ToolResult(
        text=state.get("tool_result", ""),
        confidence=state.get("confidence", 0.0),
        ok=bool(state.get("_ok", True)),
    )
    return "escalate" if needs_escalation(probe) else "respond"


def _escalate_node(state: AgentState) -> AgentState:
    """Low confidence: create a ticket and fold it into the reply."""
    ticket = run_tool(
        "create_support_ticket",
        {"user_query": state.get("query", ""), "description": state.get("tool_result", "")},
    )
    metadata = dict(state.get("tool_metadata", {}))
    ticket_id = ticket.metadata.get("ticket_id")
    metadata["ticket_id"] = ticket_id
    combined = (
        f"{state.get('tool_result', '')}\n\n"
        f"I could not confidently resolve this automatically, so it has been "
        f"escalated.\n{ticket.text}"
    ).strip()

    answer = (
        "I could not find a reliable knowledge-base match for this issue, so it has\n"
        "been escalated to the IT team.\n\n"
        f"Ticket ID: {ticket_id}\n\n"
        "Please keep this ticket ID for follow-up."
    )

    return {
        "tool_result": combined,
        "tool_metadata": metadata,
        "escalated": True,
        "ticket_id": ticket_id,
        "answer": answer,
    }


def _respond_node(state: AgentState, reasoner: Reasoner) -> AgentState:
    """Write the final message for the user."""
    result = ToolResult(
        text=state.get("tool_result", ""),
        confidence=state.get("confidence", 0.0),
        ok=bool(state.get("_ok", True)),
        metadata={**state.get("tool_metadata", {}), "ticket_id": state.get("ticket_id")},
    )
    return {"answer": reasoner.synthesize(state.get("query", ""), result)}


def build_agent(reasoner: Reasoner | None = None):
    """Compile the graph. Pass a reasoner to inject a fake one in tests."""
    active = reasoner or get_reasoner()

    # Define local wrapper functions to solve Pylance's lambda type inference issues
    def route_wrapper(state: AgentState) -> AgentState:
        return _route_node(state, active)

    def respond_wrapper(state: AgentState) -> AgentState:
        return _respond_node(state, active)

    graph = StateGraph(AgentState)
    graph.add_node("route", route_wrapper)
    graph.add_node("execute", _execute_node)
    graph.add_node("escalate", _escalate_node)
    graph.add_node("respond", respond_wrapper)

    graph.set_entry_point("route")
    graph.add_edge("route", "execute")
    graph.add_conditional_edges(
        "execute",
        _should_escalate,
        {"escalate": "escalate", "respond": "respond"},
    )
    graph.add_edge("escalate", END)
    graph.add_edge("respond", END)

    return graph.compile()


def answer_query(agent, query: str, *, persist: bool = True) -> AgentState:
    """Run one turn end to end and optionally record it in SQLite."""
    initial: AgentState = {
        "query": query,
        "tool_name": "",
        "tool_args": {},
        "route_reason": "",
        "tool_result": "",
        "tool_metadata": {},
        "confidence": 0.0,
        "escalated": False,
        "ticket_id": None,
        "answer": "",
        "llm_mode": "",
    }
    state: AgentState = agent.invoke(initial)

    if persist:
        # Logging a turn is a nice-to-have; never fail the user's request for it.
        with suppress(Exception):
            database.save_conversation(
                user_query=state.get("query", query),
                route_reason=state.get("route_reason", ""),
                tool_name=state.get("tool_name", ""),
                tool_result=state.get("tool_result", ""),
                final_response=state.get("answer", ""),
                confidence=state.get("confidence", 0.0),
                escalated=bool(state.get("escalated", False)),
                llm_mode=state.get("llm_mode", ""),
            )
    return state


def escalation_threshold() -> float:
    """Exposed for the CLI banner so the configured value is visible."""
    return settings.escalation_threshold