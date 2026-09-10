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

| File                | Role                                      |
|---------------------|-------------------------------------------|
| `agent_client.py`   | LangGraph agent + Rich CLI + demo mode    |
| `mcp_server.py`     | FastMCP server defining the four tools    |
| `database.py`       | SQLite helpers                            |
| `knowledge_base.py` | JSON loader and simple keyword search     |
| `data/helpdesk_kb.json` | Knowledge articles                   |

The same tool logic is available both through the MCP server and directly inside the agent client, guaranteeing that the demo always works even if an external MCP transport is not used.

---

### 14. Demo / Results

Running `python agent_client.py --demo` executes three scenarios and prints:

- USER QUERY
- AGENT DECISION (selected tool)
- MCP TOOL CALLED
- TOOL RESULT
- FINAL RESPONSE

Typical outcomes:

- Wi-Fi query → knowledge-base search → step-by-step reconnect instructions
- Slow computer → diagnose_issue → causes + Task Manager / Disk Cleanup steps
- Login problem → knowledge-base or diagnose → password reset guidance

Tickets are successfully created with IDs such as `TKT-20260910154321`.

---

### 15. Challenges

1. **Small model reliability** – qwen2.5:3b sometimes produces imperfect JSON; robust parsing and fallbacks were added.
2. **MCP transport** – full stdio client complexity was simplified for a reliable student demo while still keeping a proper MCP server.
3. **Python version** – code written to be compatible with modern Python (3.10–3.14).
4. **Keeping the project viva-friendly** – avoided heavy frameworks and unnecessary abstraction.

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
