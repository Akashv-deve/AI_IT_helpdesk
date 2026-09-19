# PROJECT REPORT

## AI IT Helpdesk Agent

**An Agentic AI System for Automated IT Support**

---

### 1. Project Title

**AI IT Helpdesk Agent**

---

### 2. Problem Statement

College students and staff frequently face common IT problems (Wi-Fi, login, printer, slow PC, VPN, email, software installation). Traditional helpdesks are overloaded with repetitive tickets. A simple rule-based chatbot cannot reason about the problem or select the right action. There is a need for an **agentic** system that can:

- Understand the user’s natural-language problem
- Decide which tool or knowledge source is required
- Call external tools
- Synthesize a clear, actionable response
- Escalate to a human ticket when necessary

---

### 3. Project Overview

This project implements a complete local Agentic AI Helpdesk Agent. It uses:

- **LangGraph** for a structured decision → tool → synthesis workflow
- **Ollama (qwen2.5:3b)** as a fully local large language model
- **MCP (Model Context Protocol)** to expose well-defined tools
- A local **JSON knowledge base** of IT troubleshooting articles
- **SQLite** for conversation memory and support tickets
- **Rich** for a clean terminal interface

The system never relies on paid cloud APIs.

---

### 4. Objectives

1. Demonstrate a genuine agentic workflow (not hard-coded replies).
2. Use a local open-source LLM (qwen2.5:3b via Ollama).
3. Expose IT tools through the Model Context Protocol.
4. Maintain persistent memory of conversations and tickets with SQLite.
5. Provide both interactive and demo modes for easy evaluation.
6. Keep the codebase simple enough for a student viva.

---

### 5. Proposed Solution

The agent follows this pipeline:

1. User submits an IT problem in natural language.
2. A **decision node** (LLM) selects the most appropriate MCP tool.
3. The chosen tool is executed (knowledge search, diagnosis, system info, or ticket creation).
4. A **synthesis node** (LLM) turns the raw tool result into a friendly step-by-step answer.
5. The full turn is stored in SQLite.

This separation of decision, tool use and synthesis is the hallmark of modern Agentic AI systems.

---

### 6. Agentic AI Architecture

```
┌─────────────┐
│    User     │
└──────┬──────┘
       │ natural language query
       ▼
┌──────────────────────────┐
│  LangGraph Decision Node │  ← LLM chooses tool
└──────┬───────────────────┘
       │ tool name + arguments
       ▼
┌──────────────────────────┐
│     MCP Tool Layer       │
│  • search_knowledge_base │
│  • diagnose_issue        │
│  • get_system_info       │
│  • create_support_ticket │
└──────┬───────────────────┘
       │ tool result
       ▼
┌──────────────────────────┐
│   Synthesis Node (LLM)   │  ← generates final answer
└──────┬───────────────────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐
│    User     │◄────│ SQLite Memory│
└─────────────┘     └──────────────┘
```

---

### 7. Workflow

**LangGraph nodes:**

| Node          | Responsibility                                      |
|---------------|-----------------------------------------------------|
| `decide_tool` | LLM analyzes query and outputs which tool to call   |
| `call_tool`   | Executes the selected MCP tool                      |
| `synthesize`  | LLM produces the final user-facing response         |
| `END`         | Graph terminates                                    |

Example path for “My Wi-Fi is not connecting”:

1. Decision → `search_knowledge_base_tool`
2. Tool returns troubleshooting steps from JSON KB
3. Synthesis produces a clear numbered list of actions

Example path for “Nothing worked, create a ticket”:

1. Decision → `create_support_ticket`
2. Tool inserts a row into SQLite and returns `TKT-…`
3. Synthesis confirms the ticket ID to the user

---

### 8. Technologies Used

- **Python 3.10+**
- **LangGraph** – agent orchestration
- **LangChain / langchain-ollama** – LLM interface
- **Ollama** – local model hosting (`qwen2.5:3b`)
- **MCP (mcp Python SDK)** – tool protocol
- **SQLite** – conversations & tickets
- **Rich** – terminal UI
- **JSON** – knowledge base

---

### 9. MCP Tools

Four tools are exposed by `mcp_server.py`:

1. **search_knowledge_base_tool(query)**  
   Keyword search over 16 realistic IT support entries.

2. **diagnose_issue(problem_description)**  
   Returns matched causes and ordered troubleshooting steps.

3. **get_system_info()**  
   Non-sensitive local system facts (OS, hostname, Python version, etc.).

4. **create_support_ticket(user_query, description)**  
   Creates a ticket in SQLite and returns a unique ticket ID.

---

### 10. LangGraph

A simple linear StateGraph is used:

```
decide_tool → call_tool → synthesize → END
```

State carries: `user_query`, `decision`, `tool_name`, `tool_args`, `tool_result`, `final_response`.

The decision node uses a constrained JSON prompt so the small 3B model can reliably select a tool.

---

### 11. Knowledge Base

File: `data/helpdesk_kb.json`

Contains 16 entries covering:

- Wi-Fi (connection + disconnect)
- Internet speed / no internet
- Login & password
- Printer
- Slow computer
- VPN
- Email
- Software installation / crashes
- Keyboard / mouse
- Browser
- Windows system issues

Each entry has: title, category, symptoms, causes, and ordered steps.

---

### 12. SQLite Memory

Two tables:

- **conversations** – every user turn (query, decision, tool, result, response, timestamp)
- **support_tickets** – ticket_id, query, description, status, created_at

Database file is created automatically at `data/helpdesk.db`.

---

### 13. Implementation

Key files:

| File                              | Role                                                     |
|-----------------------------------|----------------------------------------------------------|
| `main.py`                         | Zero-install entry point (press F5 in VS Code)           |
| `src/helpdesk/graph.py`           | LangGraph state machine and the escalation branch        |
| `src/helpdesk/tools.py`           | The four tools — single source of truth                  |
| `src/helpdesk/llm.py`             | Ollama reasoner plus the rule-based fallback             |
| `src/helpdesk/knowledge_base.py`  | Scored keyword retrieval with calibrated confidence      |
| `src/helpdesk/database.py`        | SQLite conversations and tickets                         |
| `src/helpdesk/mcp_server.py`      | Exposes the four tools over MCP (stdio)                  |
| `src/helpdesk/mcp_client.py`      | Real MCP client used by the `mcp-check` command          |
| `src/helpdesk/cli.py`             | Rich terminal interface                                  |
| `src/helpdesk/service.py`         | UI-facing facade: validation and error containment        |
| `app.py` + `src/web/`             | Six-page Streamlit web application                       |
| `src/helpdesk/config.py`          | Settings loaded from `.env`, with defaults               |
| `data/helpdesk_kb.json`           | 16 curated knowledge articles                            |
| `tests/`                          | 115 pytest cases, runnable without Ollama                 |

Both the MCP server and the agent import their tool implementations from
`tools.py`, so the two surfaces can never drift apart. The agent calls the tools
in-process for speed; `python main.py mcp-check` proves the MCP path works by
spawning the server over stdio, completing the handshake and invoking a tool for
real.

A design note worth highlighting: each tool returns a `ToolResult` carrying both
human-readable text and a confidence score. MCP requires a plain string, so the
server returns `.text`; the agent keeps the whole object and routes on the
score.

---

### 14. Demo / Results

Running `python main.py demo` executes four scenarios and prints, for each one:

- the user query
- the agent trace (tool chosen, why, match confidence, whether it escalated)
- the raw tool result
- the final response

Observed outcomes:

| Query | Tool | Confidence | Outcome |
|---|---|---|---|
| Wi-Fi keeps disconnecting | `diagnose_issue` | 78% | Answered with causes and steps |
| Printer says offline | `search_knowledge_base` | 65% | Answered with spooler/driver steps |
| Quantum flux capacitor misaligned | `search_knowledge_base` | 0% | **Escalated** — ticket raised |
| Show my system information | `get_system_info` | 100% | Answered directly |

The third case is the one to demonstrate: the query matches nothing, retrieval
returns no articles, the conditional edge fires, and a ticket such as
`TKT-20260917-050146-8108` is created instead of an invented answer.

Ticket IDs combine a UTC timestamp with a random suffix; a test creates 50
tickets within the same second to confirm none collide.

---

### 15. Challenges

1. **Small model reliability** – qwen2.5:3b sometimes produces imperfect JSON; robust parsing and fallbacks were added.
2. **MCP transport** – the agent calls tools in-process for speed and easier debugging, but a full stdio client (`mcp_client.py`) was still implemented so the MCP layer is verifiable rather than merely claimed. The SDK's rename of `FastMCP` to `MCPServer` in version 2.0 also required a compatibility shim so the project installs cleanly on either major version.
3. **Python version** – code written to be compatible with modern Python (3.10–3.14).
4. **Keeping the project viva-friendly** – avoided heavy frameworks and unnecessary abstraction.
5. **Making it runnable without a GPU** – a deterministic rule-based reasoner stands in when Ollama is unavailable, which also lets the test suite run in CI across Python 3.10, 3.11 and 3.12.
6. **Avoiding confident wrong answers** – retrieval originally returned the first article whenever nothing matched. Returning an empty result instead, and branching to ticket creation on low confidence, was the single most important correctness change.

---

### 16. Future Enhancements

- Multi-turn conversation memory inside the graph
- Additional tools (restart services, check disk space, open ticket portal)
- Web UI (Streamlit / Gradio)
- Retrieval-Augmented Generation with vector embeddings
- Integration with real ticketing systems (Jira, ServiceNow)
- Fine-tuning a small model on IT support dialogues

---

### 17. Conclusion

The AI IT Helpdesk Agent successfully demonstrates core Agentic AI concepts: autonomous decision making, tool use via MCP, result synthesis, and persistent memory. The entire system runs locally with free open-source components, making it ideal for academic demonstration and viva examination.

---

### 18. References

1. LangGraph documentation – https://langchain-ai.github.io/langgraph/
2. LangChain Ollama integration – https://python.langchain.com/docs/integrations/chat/ollama/
3. Model Context Protocol – https://modelcontextprotocol.io/
4. Ollama – https://ollama.com
5. Qwen2.5 model card – https://huggingface.co/Qwen/Qwen2.5-3B
6. Rich library – https://rich.readthedocs.io/
7. SQLite – https://www.sqlite.org/
