"""
AI IT Helpdesk Agent - LangGraph + MCP + Ollama (qwen2.5:3b)
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich import box

# LangChain / LangGraph
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END

# Local modules
from database import save_conversation, init_db
from knowledge_base import search_knowledge_base, format_kb_results
from database import create_ticket
import platform
import socket

console = Console()

# ---------------------------------------------------------------------------
# Direct tool implementations (used when MCP stdio process is not practical
# in a single-process student demo). These match the MCP server tools exactly
# so the architecture remains clear and the same code paths are exercised.
# ---------------------------------------------------------------------------

def _search_knowledge_base_tool(query: str) -> str:
    try:
        results = search_knowledge_base(query)
        return format_kb_results(results)
    except FileNotFoundError as e:
        return f"Error: Knowledge base file missing. {e}"
    except Exception as e:
        return f"Error searching knowledge base: {e}"


def _diagnose_issue(problem_description: str) -> str:
    try:
        results = search_knowledge_base(problem_description, top_k=2)
        if not results:
            return (
                "Unable to diagnose precisely. Please provide more details "
                "about the symptoms, error messages, and when the problem started."
            )
        parts = ["Diagnostic summary based on reported symptoms:\n"]
        for entry in results:
            causes = entry.get("causes", [])
            steps = entry.get("steps", [])
            parts.append(f"Issue match: {entry['title']}")
            parts.append("Likely causes:")
            for c in causes:
                parts.append(f"  - {c}")
            parts.append("Recommended steps:")
            for i, s in enumerate(steps, 1):
                parts.append(f"  {i}. {s}")
            parts.append("")
        return "\n".join(parts)
    except Exception as e:
        return f"Diagnosis error: {e}"


def _get_system_info() -> str:
    try:
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
        lines = [f"{k}: {v}" for k, v in info.items()]
        return "System Information:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error retrieving system info: {e}"


def _create_support_ticket(user_query: str, description: str = "") -> str:
    try:
        ticket_id = create_ticket(user_query, description)
        return (
            f"Support ticket created successfully.\n"
            f"Ticket ID: {ticket_id}\n"
            f"Status: open\n"
            f"Please keep this ticket ID for follow-up with the IT support team."
        )
    except Exception as e:
        return f"Error creating support ticket: {e}"


TOOL_REGISTRY = {
    "search_knowledge_base_tool": _search_knowledge_base_tool,
    "diagnose_issue": _diagnose_issue,
    "get_system_info": _get_system_info,
    "create_support_ticket": _create_support_ticket,
}

AVAILABLE_TOOLS = list(TOOL_REGISTRY.keys())


# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------

def get_llm():
    """Create ChatOllama instance. Raises clear error if Ollama unavailable."""
    try:
        llm = ChatOllama(
            model="qwen2.5:3b",
            temperature=0.1,
            num_predict=512,
        )
        # Quick connectivity check
        llm.invoke([HumanMessage(content="ping")])
        return llm
    except Exception as e:
        console.print(
            Panel(
                "[bold red]Ollama is not available or the model qwen2.5:3b is missing.[/bold red]\n\n"
                "Please ensure:\n"
                "1. Ollama is installed (https://ollama.com)\n"
                "2. Ollama service is running\n"
                "3. Model is pulled:  [cyan]ollama pull qwen2.5:3b[/cyan]\n\n"
                f"Underlying error: {e}",
                title="Ollama Error",
                border_style="red",
            )
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Agent State
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    user_query: str
    decision: str
    tool_name: str
    tool_args: Dict[str, Any]
    tool_result: str
    final_response: str


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

DECISION_PROMPT = """You are an IT Helpdesk decision agent.
Given the user query, choose the single most appropriate tool from the list below.
Reply with ONLY a JSON object in this exact format (no extra text):
{{"tool": "<tool_name>", "reason": "<short reason>"}}

Available tools:
- search_knowledge_base_tool : look up common IT troubleshooting steps (Wi-Fi, printer, email, password, VPN, browser, etc.)
- diagnose_issue : deeper analysis of an IT problem when symptoms need diagnosis
- get_system_info : retrieve basic local system information (OS, hostname, Python version)
- create_support_ticket : create a support ticket when the user asks to escalate or previous steps failed

User query: {query}
"""


def decide_tool(state: AgentState) -> AgentState:
    """Router node: LLM decides which MCP tool to call."""
    llm = get_llm()
    prompt = DECISION_PROMPT.format(query=state["user_query"])
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        text = response.content.strip()
        # Extract JSON even if the model adds markdown fences
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        data = json.loads(text)
        tool = data.get("tool", "search_knowledge_base_tool")
        reason = data.get("reason", "")
        if tool not in AVAILABLE_TOOLS:
            tool = "search_knowledge_base_tool"
            reason = "fallback to knowledge base"
        state["decision"] = f"Selected tool: {tool}" + (f" ({reason})" if reason else "")
        state["tool_name"] = tool

        # Build simple args
        if tool == "create_support_ticket":
            state["tool_args"] = {
                "user_query": state["user_query"],
                "description": state["user_query"],
            }
        elif tool == "get_system_info":
            state["tool_args"] = {}
        else:
            state["tool_args"] = {"query": state["user_query"]} if tool == "search_knowledge_base_tool" else {"problem_description": state["user_query"]}
    except Exception as e:
        # Safe fallback
        state["decision"] = f"Selected tool: search_knowledge_base_tool (fallback after error: {e})"
        state["tool_name"] = "search_knowledge_base_tool"
        state["tool_args"] = {"query": state["user_query"]}
    return state


def call_tool(state: AgentState) -> AgentState:
    """Execute the chosen MCP tool."""
    name = state["tool_name"]
    args = state.get("tool_args", {})
    func = TOOL_REGISTRY.get(name)
    if not func:
        state["tool_result"] = f"Unknown tool: {name}"
        return state
    try:
        if name == "get_system_info":
            result = func()
        elif name == "create_support_ticket":
            result = func(args.get("user_query", ""), args.get("description", ""))
        elif name == "diagnose_issue":
            result = func(args.get("problem_description", state["user_query"]))
        else:
            result = func(args.get("query", state["user_query"]))
        state["tool_result"] = result
    except Exception as e:
        state["tool_result"] = f"Tool execution error: {e}"
    return state


SYNTHESIZE_PROMPT = """You are a helpful IT support agent.
The user reported: {query}

You decided to use tool: {tool}
Tool returned:
{tool_result}

Write a clear, concise, step-by-step final response for the user.
Be practical and friendly. Do not mention internal tool names or JSON.
If a ticket was created, clearly show the ticket ID.
"""


def synthesize(state: AgentState) -> AgentState:
    """LLM synthesizes a user-friendly final answer from the tool result."""
    llm = get_llm()
    prompt = SYNTHESIZE_PROMPT.format(
        query=state["user_query"],
        tool=state["tool_name"],
        tool_result=state["tool_result"],
    )
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        state["final_response"] = response.content.strip()
    except Exception as e:
        # Fallback: just return the raw tool result
        state["final_response"] = (
            f"Here is the information I found:\n\n{state['tool_result']}\n\n"
            f"(Note: LLM synthesis failed: {e})"
        )
    return state


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("decide_tool", decide_tool)
    graph.add_node("call_tool", call_tool)
    graph.add_node("synthesize", synthesize)

    graph.set_entry_point("decide_tool")
    graph.add_edge("decide_tool", "call_tool")
    graph.add_edge("call_tool", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def display_turn(state: AgentState):
    console.print()
    console.print(Panel(state["user_query"], title="[bold cyan]USER QUERY[/bold cyan]", border_style="cyan"))
    console.print(Panel(state["decision"], title="[bold yellow]AGENT DECISION[/bold yellow]", border_style="yellow"))
    console.print(Panel(state["tool_name"], title="[bold magenta]MCP TOOL CALLED[/bold magenta]", border_style="magenta"))
    # Truncate very long tool results for display
    result_display = state["tool_result"]
    if len(result_display) > 1200:
        result_display = result_display[:1200] + "\n... (truncated)"
    console.print(Panel(result_display, title="[bold blue]TOOL RESULT[/bold blue]", border_style="blue"))
    console.print(Panel(Markdown(state["final_response"]), title="[bold green]FINAL RESPONSE[/bold green]", border_style="green"))
    console.print()


# ---------------------------------------------------------------------------
# Main run loop
# ---------------------------------------------------------------------------

def run_query(app, query: str) -> AgentState:
    initial: AgentState = {
        "user_query": query,
        "decision": "",
        "tool_name": "",
        "tool_args": {},
        "tool_result": "",
        "final_response": "",
    }
    result = app.invoke(initial)
    # Persist
    try:
        save_conversation(
            user_query=result["user_query"],
            decision=result["decision"],
            tool_name=result["tool_name"],
            tool_result=result["tool_result"][:2000],
            final_response=result["final_response"][:2000],
        )
    except Exception:
        pass  # non-fatal
    return result


def interactive_mode(app):
    console.print(
        Panel(
            "[bold]AI IT Helpdesk Agent[/bold]\n"
            "Type your IT problem and press Enter.\n"
            "Commands: [cyan]exit[/cyan] / [cyan]quit[/cyan] to leave.",
            title="Welcome",
            border_style="green",
        )
    )
    while True:
        try:
            query = console.input("[bold cyan]You > [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye!")
            break
        if not query:
            continue
        if query.lower() in ("exit", "quit"):
            console.print("Goodbye!")
            break
        with console.status("[bold green]Thinking...[/bold green]"):
            state = run_query(app, query)
        display_turn(state)


def demo_mode(app):
    demos = [
        "My Wi-Fi is not connecting.",
        "My computer is running very slowly.",
        "I cannot log in to my account.",
    ]
    console.print(Panel("[bold]DEMO MODE[/bold] – running 3 example IT problems", border_style="green"))
    for i, q in enumerate(demos, 1):
        console.rule(f"[bold]Demo {i}/3[/bold]")
        with console.status("[bold green]Thinking...[/bold green]"):
            state = run_query(app, q)
        display_turn(state)
    console.print("[bold green]Demo finished.[/bold green]")


def main():
    parser = argparse.ArgumentParser(description="AI IT Helpdesk Agent")
    parser.add_argument("--demo", action="store_true", help="Run 3 demo queries")
    args = parser.parse_args()

    # Ensure DB and KB exist
    init_db()
    kb_path = os.path.join(os.path.dirname(__file__), "data", "helpdesk_kb.json")
    if not os.path.exists(kb_path):
        console.print(f"[red]Knowledge base missing: {kb_path}[/red]")
        sys.exit(1)

    console.print("[dim]Building LangGraph agent...[/dim]")
    app = build_graph()

    # Connectivity check (will exit with clear message if Ollama missing)
    console.print("[dim]Checking Ollama (qwen2.5:3b)...[/dim]")
    _ = get_llm()
    console.print("[green]Ollama ready.[/green]")

    if args.demo:
        demo_mode(app)
    else:
        interactive_mode(app)


if __name__ == "__main__":
    main()
