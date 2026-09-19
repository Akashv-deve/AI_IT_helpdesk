"""Application service layer.

Everything the user interface needs, exposed as plain Python with no Streamlit,
Rich or argparse anywhere in sight. The web UI, the CLI and the test suite all
drive the agent through this one class.

Two reasons it exists rather than having the UI call ``graph.py`` directly:

* **Testability.** Every UI behaviour — repeated queries, escalation, empty
  input, Ollama being down — can be asserted without rendering a single widget.
* **Error containment.** A helpdesk tool is used by people who should never see
  a traceback. Every method here converts failure into a readable message.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from typing import Any

from . import database
from .config import settings
from .graph import answer_query, build_agent
from .knowledge_base import KBEntry, KnowledgeBaseError, categories, load_kb, tokenize
from .llm import Reasoner, get_reasoner, ollama_status

MAX_QUERY_LENGTH = 2000


@dataclass(frozen=True)
class TurnResult:
    """One completed question-and-answer exchange, safe to render anywhere."""

    query: str
    answer: str = ""
    tool_name: str = ""
    route_reason: str = ""
    confidence: float = 0.0
    escalated: bool = False
    ticket_id: str | None = None
    llm_mode: str = ""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class HealthCheck:
    """One row of the diagnostics report."""

    name: str
    status: str  # "ok" | "warn" | "fail"
    detail: str
    hint: str = ""


@dataclass
class Dashboard:
    """Counters for the status screen."""

    kb_articles: int = 0
    kb_categories: int = 0
    conversations: int = 0
    escalations: int = 0
    open_tickets: int = 0
    total_tickets: int = 0
    llm_mode: str = ""
    model: str = ""
    ollama_online: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def escalation_rate(self) -> float:
        return self.escalations / self.conversations if self.conversations else 0.0


class HelpdeskService:
    """The one object a user interface needs.

    The agent and reasoner are built lazily on first use, so constructing the
    service is instant and a missing Ollama never blocks application startup.
    """

    def __init__(self, force_offline: bool = False) -> None:
        self.force_offline = force_offline
        self._reasoner: Reasoner | None = None
        self._agent: Any | None = None
        database.init_db()

    # -- lazy wiring ------------------------------------------------------

    @property
    def reasoner(self) -> Reasoner:
        if self._reasoner is None:
            self._reasoner = get_reasoner(force_offline=self.force_offline)
        return self._reasoner

    @property
    def agent(self) -> Any:
        if self._agent is None:
            self._agent = build_agent(self.reasoner)
        return self._agent

    @property
    def llm_mode(self) -> str:
        """Human-readable description of what is doing the reasoning."""
        return self.reasoner.mode

    @property
    def is_offline(self) -> bool:
        """True when answers come from the deterministic fallback, not a model."""
        return "ollama" not in self.reasoner.mode.lower()

    @property
    def mode_label(self) -> str:
        return "Offline fallback mode" if self.is_offline else "Ollama AI mode"

    # -- the main entry point ---------------------------------------------

    def ask(self, query: str, *, persist: bool = True) -> TurnResult:
        """Run one turn through the LangGraph agent.

        Never raises. Invalid input and internal failures come back as a
        ``TurnResult`` with ``error`` set and ``ok`` False.
        """
        cleaned = (query or "").strip()
        if not cleaned:
            return TurnResult(
                query="",
                error="Please describe the problem before sending.",
            )
        if len(cleaned) > MAX_QUERY_LENGTH:
            return TurnResult(
                query=cleaned[:120] + "…",
                error=(
                    f"That message is {len(cleaned):,} characters. "
                    f"Please shorten it to under {MAX_QUERY_LENGTH:,}."
                ),
            )

        try:
            state = answer_query(self.agent, cleaned, persist=persist)
        except KnowledgeBaseError as exc:
            return TurnResult(
                query=cleaned,
                error=f"The knowledge base could not be read: {exc}",
                llm_mode=self._safe_mode(),
            )
        except Exception as exc:
            return TurnResult(
                query=cleaned,
                error=(
                    "Something went wrong while handling that request "
                    f"({type(exc).__name__}). Please try again, or raise a ticket "
                    "from the Tickets page."
                ),
                llm_mode=self._safe_mode(),
            )

        return TurnResult(
            query=cleaned,
            answer=state.get("answer", ""),
            tool_name=state.get("tool_name", ""),
            route_reason=state.get("route_reason", ""),
            confidence=float(state.get("confidence", 0.0)),
            escalated=bool(state.get("escalated", False)),
            ticket_id=state.get("ticket_id"),
            llm_mode=state.get("llm_mode", "") or self._safe_mode(),
        )

    def _safe_mode(self) -> str:
        try:
            return self.reasoner.mode
        except Exception:
            return "unavailable"

    # -- tickets -----------------------------------------------------------

    def tickets(self, limit: int = 100, status: str | None = None) -> list[database.Ticket]:
        try:
            return database.list_tickets(limit=limit, status=status)
        except Exception:
            return []

    def set_ticket_status(self, ticket_id: str, status: str) -> tuple[bool, str]:
        """Return ``(changed, message)`` — never raises on a bad status."""
        if status not in database.VALID_STATUSES:
            allowed = ", ".join(database.VALID_STATUSES)
            return False, f"'{status}' is not a valid status. Use one of: {allowed}."
        try:
            changed = database.update_ticket_status(ticket_id, status)
        except Exception as exc:
            return False, f"Could not update the ticket: {exc}"
        if not changed:
            return False, f"No ticket found with ID {ticket_id}."
        return True, f"{ticket_id} moved to {status}."

    # -- history -----------------------------------------------------------

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        try:
            return database.recent_conversations(limit=limit)
        except Exception:
            return []

    # -- knowledge base ----------------------------------------------------

    def kb_categories(self) -> list[str]:
        try:
            return categories()
        except KnowledgeBaseError:
            return []

    def kb_articles(self, category: str | None = None, search: str = "") -> list[KBEntry]:
        """Browse the knowledge base with optional category and text filtering."""
        try:
            entries = list(load_kb())
        except KnowledgeBaseError:
            return []

        if category and category.lower() != "all":
            entries = [entry for entry in entries if entry.category == category]

        terms = tokenize(search)
        if terms:
            def matches(entry: KBEntry) -> bool:
                haystack = tokenize(
                    " ".join(
                        [entry.title, entry.category.replace("_", " "), *entry.symptoms,
                         *entry.causes, *entry.steps]
                    )
                )
                return bool(terms & haystack)

            entries = [entry for entry in entries if matches(entry)]

        return entries

    # -- dashboard and diagnostics ----------------------------------------

    def dashboard(self) -> Dashboard:
        """Counters for the status screen. Degrades instead of raising."""
        board = Dashboard(model=settings.ollama_model)

        try:
            board.kb_articles = len(load_kb())
            board.kb_categories = len(categories())
        except KnowledgeBaseError as exc:
            board.warnings.append(f"Knowledge base unreadable: {exc}")

        try:
            counts = database.stats()
            board.conversations = counts["conversations"]
            board.escalations = counts["escalations"]
            board.open_tickets = counts["open_tickets"]
            board.total_tickets = len(database.list_tickets(limit=10_000))
        except Exception as exc:
            board.warnings.append(f"Database unreadable: {exc}")

        board.llm_mode = self.mode_label
        board.ollama_online = not self.is_offline
        return board

    def health(self) -> list[HealthCheck]:
        """The same checks the ``doctor`` CLI command reports."""
        checks: list[HealthCheck] = []

        # Python environment — version and OS family only. Nothing identifying.
        checks.append(
            HealthCheck(
                name="Python environment",
                status="ok" if sys.version_info >= (3, 10) else "fail",
                detail=f"Python {platform.python_version()} on {platform.system()}",
                hint=(
                    ""
                    if sys.version_info >= (3, 10)
                    else "This project needs Python 3.10 or newer."
                ),
            )
        )

        try:
            entries = load_kb()
            checks.append(
                HealthCheck(
                    name="Knowledge base",
                    status="ok",
                    detail=f"{len(entries)} articles across {len(categories())} categories",
                    hint=str(settings.kb_path),
                )
            )
        except KnowledgeBaseError as exc:
            checks.append(
                HealthCheck(
                    name="Knowledge base",
                    status="fail",
                    detail=str(exc),
                    hint="Restore data/helpdesk_kb.json or fix KB_PATH in .env",
                )
            )

        try:
            database.init_db()
            counts = database.stats()
            checks.append(
                HealthCheck(
                    name="SQLite database",
                    status="ok",
                    detail=(
                        f"{counts['conversations']} conversations · "
                        f"{counts['open_tickets']} open tickets"
                    ),
                    hint=str(settings.db_path),
                )
            )
        except Exception as exc:
            checks.append(
                HealthCheck(
                    name="SQLite database",
                    status="fail",
                    detail=str(exc),
                    hint="Check that the data/ directory is writable",
                )
            )

        if self.force_offline or settings.offline_forced:
            checks.append(
                HealthCheck(
                    name="Ollama",
                    status="warn",
                    detail="Skipped — offline mode was requested",
                    hint="Unset HELPDESK_OFFLINE or clear the offline toggle to use the model",
                )
            )
        else:
            online, detail = ollama_status()
            checks.append(
                HealthCheck(
                    name="Ollama",
                    status="ok" if online else "warn",
                    detail=detail,
                    hint=(
                        ""
                        if online
                        else f"Install from https://ollama.com, then run: "
                        f"ollama pull {settings.ollama_model}"
                    ),
                )
            )

        checks.append(
            HealthCheck(
                name="Reasoning mode",
                status="ok" if not self.is_offline else "warn",
                detail=self.mode_label,
                hint=(
                    ""
                    if not self.is_offline
                    else "Answers come from deterministic keyword rules, not a language model."
                ),
            )
        )
        return checks

    def mcp_health(self) -> HealthCheck:
        """Spawn the MCP server over stdio and confirm it advertises its tools.

        Kept out of :meth:`health` because it starts a subprocess and takes a
        second or two — the UI calls it on demand, behind a button.
        """
        try:
            from .mcp_client import list_tools_sync

            remote = list_tools_sync()
        except ModuleNotFoundError:
            return HealthCheck(
                name="MCP server",
                status="warn",
                detail="The MCP SDK is not installed",
                hint="pip install -r requirements.txt",
            )
        except Exception as exc:
            return HealthCheck(
                name="MCP server",
                status="fail",
                detail=f"Handshake failed: {exc}",
                hint="Try running: python main.py mcp-check",
            )

        names = ", ".join(tool.name for tool in remote)
        return HealthCheck(
            name="MCP server",
            status="ok",
            detail=f"{len(remote)} tools advertised over stdio",
            hint=names,
        )
