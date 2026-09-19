# AI IT Helpdesk Agent

A local-first agentic IT helpdesk that routes technical issues, retrieves
troubleshooting guidance, escalates low-confidence cases, and persists support
tickets using **LangGraph, Ollama, MCP, Streamlit, and SQLite**.

[![CI](https://github.com/Akashv-deve/AI_IT_helpdesk/actions/workflows/ci.yml/badge.svg)](https://github.com/Akashv-deve/AI_IT_helpdesk/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Workflow-blueviolet.svg)](https://www.langchain.com/langgraph)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-black.svg)](https://ollama.com/)
[![MCP](https://img.shields.io/badge/MCP-Tool%20Protocol-orange.svg)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/Tests-115%20passing-success.svg)](tests/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Demo

**[▶ Watch the full project demo](./demo/AI_IT_Helpdesk_Demo.mp4)**

The demo shows the complete workflow:

```text
User Query
    ↓
LangGraph Routing
    ↓
Tool Execution
    ↓
Retrieval Confidence Check
    ├── High confidence → Response
    └── Low confidence  → Support Ticket → Response
