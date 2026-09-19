"""Command-line interface.

    python -m helpdesk                 interactive chat
    python -m helpdesk ask "..."       one question, one answer
    python -m helpdesk demo            scripted walkthrough for a viva/demo
    python -m helpdesk tickets         list escalated tickets
    python -m helpdesk history         recent conversation turns
    python -m helpdesk doctor          check Ollama, the KB and the database
    python -m helpdesk mcp-check       prove the MCP server works over stdio
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from . import __version__, database
from .config import settings
from .graph import answer_query, build_agent
from .knowledge_base import KnowledgeBaseError
from .llm import get_reasoner
from .service import HelpdeskService

console = Console()

DEMO_QUERIES = (
    "My Wi-Fi keeps disconnecting every few minutes.",
    "The office printer says offline and nothing prints.",
    "My quantum flux capacitor is misaligned.",  # deliberately unmatched -> escalation
    "Show me my system information.",
)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_turn(state: dict, *, verbose: bool) -> None:
    if verbose:
        trace = Table(box=None, show_header=False, pad_edge=False)
        trace.add_column(style="dim", no_wrap=True)
        trace.add_column()
        trace.add_row("tool", state.get("tool_name", "—"))
        trace.add_row("why", state.get("route_reason", "—"))
        trace.add_row("confidence", f"{state.get('confidence', 0.0):.0%}")
        trace.add_row("escalated", "yes" if state.get("escalated") else "no")
        if state.get("ticket_id"):
            trace.add_row("ticket", state["ticket_id"])
        console.print(Panel(trace, title="[dim]agent trace[/dim]", border_style="grey37"))

        result = state.get("tool_result", "")
        if len(result) > 1200:
            result = result[:1200] + "\n… (truncated)"
        console.print(Panel(result, title="[blue]tool result[/blue]", border_style="blue"))

    console.print(
        Panel(
            Markdown(state.get("answer", "")),
            title="[bold green]Helpdesk[/bold green]",
            border_style="green",
        )
    )


def _banner(reasoner_mode: str) -> None:
    offline = "ollama" not in reasoner_mode
    console.print(
        Panel(
            f"[bold]AI IT Helpdesk[/bold]  v{__version__}\n"
            f"reasoning: [cyan]{reasoner_mode}[/cyan]\n"
            f"escalates below: [cyan]{settings.escalation_threshold:.0%}[/cyan]"
            " match confidence\n\n"
            "Describe your IT problem, or type [cyan]exit[/cyan] to quit."
            + (
                "\n\n[yellow]Ollama was not reachable, so answers come from the "
                "deterministic fallback. Run [cyan]python -m helpdesk doctor[/cyan] "
                "for details.[/yellow]"
                if offline
                else ""
            ),
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_chat(args: argparse.Namespace) -> int:
    agent = build_agent(get_reasoner(force_offline=args.offline))
    _banner(get_reasoner(force_offline=args.offline).mode)
    while True:
        try:
            query = console.input("\n[bold cyan]you ›[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            return 0
        if not query:
            continue
        if query.lower() in ("exit", "quit", ":q"):
            console.print("[dim]Goodbye.[/dim]")
            return 0
        with console.status("[green]thinking…[/green]"):
            state = answer_query(agent, query)
        _render_turn(state, verbose=args.verbose)


def cmd_ask(args: argparse.Namespace) -> int:
    agent = build_agent(get_reasoner(force_offline=args.offline))
    with console.status("[green]thinking…[/green]"):
        state = answer_query(agent, args.query)
    _render_turn(state, verbose=args.verbose)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    reasoner = get_reasoner(force_offline=args.offline)
    agent = build_agent(reasoner)
    console.print(
        Panel(
            f"[bold]Demo[/bold] — {len(DEMO_QUERIES)} scripted problems, "
            f"reasoning via [cyan]{reasoner.mode}[/cyan].\n"
            "The third one is intentionally nonsense, to show the agent escalating "
            "instead of inventing an answer.",
            border_style="green",
        )
    )
    for index, query in enumerate(DEMO_QUERIES, start=1):
        console.rule(f"[bold]{index}/{len(DEMO_QUERIES)}[/bold]  {query}")
        with console.status("[green]thinking…[/green]"):
            state = answer_query(agent, query)
        _render_turn(state, verbose=True)
    console.print("[bold green]Demo complete.[/bold green]")
    return 0


def cmd_tickets(args: argparse.Namespace) -> int:
    tickets = database.list_tickets(limit=args.limit, status=args.status)
    if not tickets:
        console.print("[dim]No tickets yet. Escalate one from a chat session.[/dim]")
        return 0
    table = Table(title="Support tickets")
    table.add_column("Ticket ID", style="cyan", no_wrap=True)
    table.add_column("Status", style="magenta")
    table.add_column("Reported problem")
    table.add_column("Created (UTC)", style="dim", no_wrap=True)
    for ticket in tickets:
        problem = ticket.user_query
        summary = problem if len(problem) <= 60 else problem[:57] + "…"
        table.add_row(ticket.ticket_id, ticket.status, summary, ticket.created_at)
    console.print(table)
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    rows = database.recent_conversations(limit=args.limit)
    if not rows:
        console.print("[dim]No conversations recorded yet.[/dim]")
        return 0
    table = Table(title="Recent turns")
    table.add_column("#", style="dim", no_wrap=True)
    table.add_column("Query")
    table.add_column("Tool", style="cyan")
    table.add_column("Conf.", justify="right")
    table.add_column("Esc.", justify="center")
    for row in rows:
        query = row["user_query"]
        table.add_row(
            str(row["id"]),
            query if len(query) <= 50 else query[:47] + "…",
            row["tool_name"] or "—",
            f"{(row['confidence'] or 0):.0%}",
            "yes" if row["escalated"] else "—",
        )
    console.print(table)
    summary = database.stats()
    turns = summary["conversations"]
    tickets = summary["open_tickets"]
    console.print(
        f"[dim]{turns} turn{'' if turns == 1 else 's'} · "
        f"{summary['escalations']} escalated · "
        f"{tickets} open ticket{'' if tickets == 1 else 's'}[/dim]"
    )
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    """Report the same checks the web UI's Diagnostics page shows."""
    service = HelpdeskService()
    checks = service.health()

    styles = {"ok": "[green]ok[/green]", "warn": "[yellow]warn[/yellow]", "fail": "[red]fail[/red]"}
    table = Table(title="Environment check")
    table.add_column("Check", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Detail")
    for check in checks:
        detail = check.detail + (f"\n[dim]{check.hint}[/dim]" if check.hint else "")
        table.add_row(check.name, styles.get(check.status, check.status), detail)
    console.print(table)

    if service.is_offline:
        console.print(
            "[yellow]Running in offline fallback mode — the agent still works, "
            "but answers come from deterministic rules rather than a model.[/yellow]"
        )
    return 1 if any(check.status == "fail" for check in checks) else 0


def cmd_mcp_check(_: argparse.Namespace) -> int:
    """Spawn the MCP server over stdio and exercise it for real."""
    from .mcp_client import call_tool_sync, list_tools_sync

    try:
        with console.status("[green]starting MCP server over stdio…[/green]"):
            remote_tools = list_tools_sync()
    except Exception as exc:
        console.print(Panel(f"MCP handshake failed: {exc}", border_style="red", title="fail"))
        return 1

    table = Table(title="Tools advertised over MCP")
    table.add_column("Tool", style="cyan", no_wrap=True)
    table.add_column("Description")
    for tool in remote_tools:
        first_line = tool.description.splitlines()[0] if tool.description else "—"
        table.add_row(tool.name, first_line)
    console.print(table)

    with console.status("[green]calling get_system_info over MCP…[/green]"):
        output = call_tool_sync("get_system_info", {})
    console.print(Panel(output, title="[blue]live MCP tool call[/blue]", border_style="blue"))
    return 0


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="helpdesk",
        description="AI IT Helpdesk — a LangGraph agent with MCP tools and a local LLM.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    def add_shared(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--offline",
            action="store_true",
            help="skip Ollama and use deterministic rule-based reasoning",
        )
        sub.add_argument(
            "-v", "--verbose", action="store_true", help="show the agent's routing trace"
        )

    chat = subparsers.add_parser("chat", help="interactive session (default)")
    add_shared(chat)
    chat.set_defaults(func=cmd_chat)

    ask = subparsers.add_parser("ask", help="answer a single question and exit")
    ask.add_argument("query", help="the IT problem to solve")
    add_shared(ask)
    ask.set_defaults(func=cmd_ask)

    demo = subparsers.add_parser("demo", help="run the scripted demo")
    add_shared(demo)
    demo.set_defaults(func=cmd_demo)

    tickets = subparsers.add_parser("tickets", help="list support tickets")
    tickets.add_argument("--limit", type=int, default=20)
    tickets.add_argument(
        "--status", choices=database.VALID_STATUSES, help="filter by ticket status"
    )
    tickets.set_defaults(func=cmd_tickets)

    history = subparsers.add_parser("history", help="show recent conversation turns")
    history.add_argument("--limit", type=int, default=10)
    history.set_defaults(func=cmd_history)

    doctor = subparsers.add_parser("doctor", help="check the environment")
    doctor.set_defaults(func=cmd_doctor)

    mcp_check = subparsers.add_parser("mcp-check", help="exercise the MCP server over stdio")
    mcp_check.set_defaults(func=cmd_mcp_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:  # bare `python -m helpdesk` starts a chat
        args = parser.parse_args(["chat", *(argv or [])])

    database.init_db()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        return 130
    except KnowledgeBaseError as exc:
        console.print(Panel(str(exc), title="[red]Knowledge base error[/red]", border_style="red"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
