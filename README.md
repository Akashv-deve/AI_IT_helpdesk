# AI IT Helpdesk Agent

> A local-first agentic IT helpdesk that routes user issues, retrieves
> troubleshooting guidance, escalates low-confidence cases, and persists
> tickets using LangGraph, Ollama, MCP, Streamlit, and SQLite.

[![CI](https://github.com/Akashv-deve/AI_IT_helpdesk/actions/workflows/ci.yml/badge.svg)](https://github.com/Akashv-deve/AI_IT_helpdesk/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Orchestration-blueviolet.svg)](https://www.langchain.com/langgraph)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-black.svg)](https://ollama.com/)
[![MCP](https://img.shields.io/badge/MCP-Tool%20Protocol-orange.svg)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/Tests-115%20passing-success.svg)](tests/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Overview

AI IT Helpdesk Agent is a local-first support system for common IT problems
such as Wi-Fi, printers, VPN, login issues, software problems, and slow
computers.

The system uses a LangGraph workflow to select a tool, execute it, evaluate
the resulting retrieval confidence, and either answer the user or escalate
the issue into a support ticket. When Ollama is unavailable, a deterministic
rule-based reasoner keeps the application usable without an LLM.

## Key Features

- **LangGraph Agent Workflow** — structured routing, tool execution, and
  confidence-based branching.
- **Local LLM** — Ollama with `qwen2.5:3b` for local reasoning and response
  generation.
- **Confidence-Based Escalation** — low-confidence results are escalated to a
  support ticket instead of producing an unsupported solution.
- **Deterministic Fallback** — rule-based routing and responses when Ollama is
  unavailable or offline mode is enabled.
- **MCP Integration** — the same four tool implementations are exposed through
  an MCP stdio server and verified using a real MCP client handshake.
- **Persistent Support Desk** — SQLite stores conversations and support
  tickets.
- **Streamlit Web UI** — Helpdesk, Tickets, History, Knowledge Base,
  Dashboard, and Diagnostics pages.
- **Rich CLI** — interactive chat, demo, diagnostics, ticket and history
  commands.
- **115 Automated Tests** — pytest and Streamlit `AppTest` coverage.
- **GitHub Actions CI** — automated linting, testing, CLI smoke tests, and web
  application checks.

---

## Architecture

```mermaid
flowchart TD
    U[User Query] --> R[Route]
    R --> E[Execute Tool]
    E --> C{Confidence Check}

    C -->|High confidence| S[Respond]
    C -->|Low confidence| X[Create Support Ticket]
    X --> S

    R -. Ollama available .-> L[Ollama qwen2.5:3b]
    R -. Ollama unavailable .-> F[Rule-Based Fallback]

    E --> K[(JSON Knowledge Base)]
    E --> D[(SQLite)]
    X --> D

    MCP[MCP stdio Server] --> T[Shared Tool Implementations]
    E --> T
Agent workflow
route
  ↓
execute
  ↓
confidence check
 ├── high confidence → respond
 └── low confidence  → escalate → respond

The important design decision is the escalation branch: when the system does
not have enough retrieval evidence, it creates a support ticket instead of
pretending it has a reliable answer.

Core Tools

The agent has four tool implementations:

Tool	Purpose
search_knowledge_base	Search the local IT knowledge base
diagnose_issue	Analyse a problem and return likely causes and steps
get_system_info	Return basic local system information
create_support_ticket	Create a support ticket in SQLite

The implementations live in src/helpdesk/tools.py and are reused by the
agent and MCP server.

MCP Integration

The project exposes the same helpdesk tools through a Model Context Protocol
(MCP) server over stdio.

The normal LangGraph agent calls the shared Python implementations in-process.
The MCP server provides a separate protocol surface that can be verified
independently.

Run the verification with:

python main.py mcp-check

This performs an MCP stdio handshake and verifies the advertised tools.

Technology Stack
Layer	Technology
Language	Python
Agent orchestration	LangGraph
Local LLM	Ollama + qwen2.5:3b
Tool protocol	Model Context Protocol (MCP)
Web UI	Streamlit
CLI	Rich
Storage	SQLite
Knowledge base	JSON
Testing	pytest + Streamlit AppTest
Linting / CI	Ruff + GitHub Actions
Screenshots
Helpdesk

Confidence-Based Escalation

Ticket Management

Dashboard

Diagnostics

Screenshot files are stored in docs/screenshots/.

Installation
1. Clone the repository
git clone https://github.com/Akashv-deve/AI_IT_helpdesk.git
cd AI_IT_helpdesk
2. Create a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

If PowerShell blocks activation:

Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
3. Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

For development and testing:

pip install -r requirements-dev.txt
4. Optional: enable local Ollama reasoning

Install Ollama and pull the configured model:

ollama pull qwen2.5:3b

Ollama is optional. Without it, the application uses the deterministic
rule-based fallback.

Running
Web application
streamlit run app.py

The application opens at:

http://localhost:8501
CLI
python main.py
Useful CLI commands
python main.py ask "my wifi keeps dropping" -v
python main.py demo
python main.py tickets --status open
python main.py history
python main.py doctor
python main.py mcp-check
Offline mode

For a deterministic demo without Ollama:

$env:HELPDESK_OFFLINE = "1"
streamlit run app.py

The web application also provides a Force offline mode option.

Testing

The repository contains 115 automated tests covering:

knowledge-base retrieval
LangGraph routing and escalation
SQLite persistence
tool contracts
MCP server behaviour
service-layer validation
Streamlit pages and user flows

Run the full suite:

pytest

Run linting:

ruff check src tests main.py app.py

GitHub Actions runs the test and lint workflow automatically.

Placement Demo

A short demonstration can show the complete workflow:

Open the Helpdesk page and submit a known IT issue.
Expand Agent Details to show the selected tool and retrieval confidence.
Submit an unsupported problem and demonstrate automatic escalation.
Open Tickets to show the generated support ticket.
Open History to show the persisted conversation.
Open Diagnostics and run the MCP handshake.
Switch to offline mode to demonstrate deterministic fallback behaviour.

This demonstrates the project as an agentic helpdesk system rather than a
simple chat interface.

Knowledge Base

The project includes a local JSON knowledge base containing 16 IT support
articles covering areas such as:

Wi-Fi
Internet connectivity
Login and passwords
Printers
Slow computers
VPN
Email
Software
Keyboard and mouse
Browsers
Windows issues

The knowledge base is stored at:

data/helpdesk_kb.json
Limitations
Retrieval is based on transparent keyword scoring, so heavily paraphrased
issues may produce weaker matches.
The current knowledge base contains 16 curated articles.
Conversation history is persisted, but follow-up questions are not currently
fed back into the agent as conversational context.
The application is designed for local use and demonstration rather than
multi-user production deployment.
The retrieval confidence score represents a knowledge-base match score, not a
calibrated probability of correctness.
Project Structure
AI_IT_helpdesk/
├── app.py
├── main.py
├── data/
│   └── helpdesk_kb.json
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PROJECT_REPORT.md
│   └── screenshots/
├── src/
│   ├── helpdesk/
│   │   ├── cli.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── graph.py
│   │   ├── knowledge_base.py
│   │   ├── llm.py
│   │   ├── mcp_client.py
│   │   ├── mcp_server.py
│   │   ├── service.py
│   │   └── tools.py
│   └── web/
│       ├── pages/
│       ├── runner.py
│       ├── state.py
│       └── theme.py
├── tests/
├── .env.example
├── .github/
├── .streamlit/
├── .vscode/
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
Documentation
Architecture
Project Report
License

MIT License — see LICENSE.