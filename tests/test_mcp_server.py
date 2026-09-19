"""The MCP surface must stay in sync with the in-process tools."""

from __future__ import annotations

import pytest

from helpdesk import tools

mcp_server = pytest.importorskip("helpdesk.mcp_server", reason="MCP SDK not installed")


def test_server_object_exists():
    assert mcp_server.server is not None


def test_mcp_exposes_exactly_the_registered_tools():
    exposed = {
        name
        for name in dir(mcp_server)
        if callable(getattr(mcp_server, name)) and name in tools.TOOLS
    }
    assert exposed == set(tools.TOOLS)


def test_mcp_wrappers_return_plain_strings():
    assert isinstance(mcp_server.get_system_info(), str)
    assert isinstance(mcp_server.search_knowledge_base("wifi"), str)
    assert isinstance(mcp_server.diagnose_issue("slow computer"), str)


def test_mcp_wrapper_matches_the_underlying_tool():
    assert mcp_server.search_knowledge_base("printer offline") == (
        tools.search_knowledge_base("printer offline").text
    )
