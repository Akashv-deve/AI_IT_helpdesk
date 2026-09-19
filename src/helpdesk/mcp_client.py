"""MCP client — talks to ``mcp_server.py`` over a real stdio session.

The agent calls tools in-process by default because it is faster and easier to
debug. This module proves the MCP layer is genuinely wired up rather than
decorative: ``python -m helpdesk mcp-check`` spawns the server as a subprocess,
performs the protocol handshake, lists the advertised tools and invokes one.

That distinction is worth making explicit — an "MCP project" where nothing ever
speaks MCP is the first thing an interviewer will poke at.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import PROJECT_ROOT


@dataclass(frozen=True)
class RemoteTool:
    name: str
    description: str


def _server_params() -> StdioServerParameters:
    """Launch the server with this repo's ``src`` on the import path."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "helpdesk.mcp_server"],
        cwd=str(PROJECT_ROOT),
        env={"PYTHONPATH": str(PROJECT_ROOT / "src")},
    )


async def list_tools() -> list[RemoteTool]:
    """Handshake with the server and return the tools it advertises."""
    async with (
        stdio_client(_server_params()) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        response = await session.list_tools()
        return [
            RemoteTool(name=tool.name, description=(tool.description or "").strip())
            for tool in response.tools
        ]


async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> str:
    """Invoke one tool over MCP and return its text content."""
    async with (
        stdio_client(_server_params()) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        response = await session.call_tool(name, arguments or {})
        chunks = [
            block.text for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        return "\n".join(chunks).strip()


def list_tools_sync() -> list[RemoteTool]:
    """Blocking wrapper for the CLI."""
    return asyncio.run(list_tools())


def call_tool_sync(name: str, arguments: dict[str, Any] | None = None) -> str:
    """Blocking wrapper for the CLI."""
    return asyncio.run(call_tool(name, arguments))
