"""MCP server — exposes the helpdesk tools over the Model Context Protocol.

Run it standalone::

    python -m helpdesk.mcp_server

It speaks stdio, so any MCP client (this project's own agent, Claude Desktop,
the MCP Inspector) can drive the same four tools.

The import shim below matters: the SDK renamed ``FastMCP`` to ``MCPServer`` in
mcp 2.0, and a single hard-coded import breaks for everyone on the other major
version. Supporting both means ``pip install -r requirements.txt`` works today
and still works after the next release.
"""

from __future__ import annotations

import sys

from . import database, tools

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ModuleNotFoundError:  # pragma: no cover - depends on installed version
    try:  # mcp < 2.0
        from mcp.server.fastmcp import FastMCP as _Server
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise SystemExit(
            "The MCP SDK is not installed. Run: pip install -r requirements.txt"
        ) from exc

server = _Server("ai-it-helpdesk")


@server.tool()
def search_knowledge_base(query: str) -> str:
    """Search the local IT knowledge base for troubleshooting steps.

    Use for common problems: Wi-Fi, printers, email, passwords, VPN, browsers,
    slow computers, software installation.
    """
    return tools.search_knowledge_base(query).text


@server.tool()
def diagnose_issue(problem_description: str) -> str:
    """Analyse an IT problem and return probable causes plus recommended steps.

    Use when the report is vague or has several symptoms and needs more than a
    direct knowledge-base lookup.
    """
    return tools.diagnose_issue(problem_description).text


@server.tool()
def get_system_info() -> str:
    """Return basic local machine details: OS, release, architecture, hostname,
    and Python version. Collects nothing private or sensitive.
    """
    return tools.get_system_info().text


@server.tool()
def create_support_ticket(user_query: str, description: str = "") -> str:
    """Create a support ticket in the local SQLite database and return its ID.

    Use when the problem cannot be resolved automatically or the user asks for
    a human technician.
    """
    return tools.create_support_ticket(user_query, description).text


def main() -> None:
    """Entry point: prepare storage, then serve over stdio."""
    database.init_db()
    # stdout is the protocol channel — anything printed there corrupts the
    # stream, so status messages must go to stderr.
    print("ai-it-helpdesk MCP server listening on stdio", file=sys.stderr)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
