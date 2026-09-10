"""
MCP Server for AI IT Helpdesk Agent.
Exposes tools via the Model Context Protocol over stdio.
Compatible with mcp >= 2.0 (MCPServer API).
"""

import platform
import socket

from mcp.server.mcpserver import MCPServer

from knowledge_base import search_knowledge_base, format_kb_results
from database import create_ticket

# Create MCP server
server = MCPServer("IT Helpdesk MCP Server")


@server.tool()
def search_knowledge_base_tool(query: str) -> str:
    """
    Search the local IT knowledge base for troubleshooting information.
    Use this when the user describes a common IT problem such as Wi-Fi,
    printer, email, password, VPN, slow computer, etc.
    """
    try:
        results = search_knowledge_base(query)
        return format_kb_results(results)
    except FileNotFoundError as e:
        return f"Error: Knowledge base file missing. {e}"
    except Exception as e:
        return f"Error searching knowledge base: {e}"


@server.tool()
def diagnose_issue(problem_description: str) -> str:
    """
    Analyze an IT problem and return possible causes with recommended
    troubleshooting steps. Use when the issue needs deeper diagnosis
    rather than a simple knowledge-base lookup.
    """
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


@server.tool()
def get_system_info() -> str:
    """
    Return basic local computer information (OS, Python version, hostname, platform).
    Does not collect any private or sensitive user data.
    """
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


@server.tool()
def create_support_ticket(user_query: str, description: str = "") -> str:
    """
    Create a support ticket when the issue cannot be resolved automatically.
    Stores the ticket in the local SQLite database and returns a ticket ID.
    """
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


if __name__ == "__main__":
    # Run over stdio (standard for local MCP)
    server.run(transport="stdio")
