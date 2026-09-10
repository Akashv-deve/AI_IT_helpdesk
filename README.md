# AI IT Helpdesk Agent

A college-level **Agentic AI** project that demonstrates a working IT support agent using **LangGraph**, **MCP (Model Context Protocol)**, **Ollama (qwen2.5:3b)**, and **SQLite**.

The agent understands a user’s IT problem, decides which tool is needed, calls the appropriate MCP tool, and synthesizes a helpful final response.

---

## 1. Project Overview

The AI IT Helpdesk Agent handles common campus/office IT issues such as:

- Wi-Fi not connecting
- Internet slow
- Password / login problems
- Computer running slowly
- Printer not working
- Software installation issues
- VPN problems
- Email problems
- Basic system troubleshooting

It follows a genuine agentic workflow (decision → tool use → synthesis) rather than hard-coded if-else replies.

---

## 2. Architecture

```
User Query
    ↓
LangGraph Router / Decision Agent  (LLM chooses tool)
    ↓
Select appropriate MCP tool
    ↓
MCP Tool execution
    ↓
Tool result
    ↓
LLM synthesizes final response
    ↓
User + SQLite memory
```

**LangGraph stages:** `decide_tool` → `call_tool` → `synthesize` → `END`

---

## 3. Technologies

| Component       | Technology              |
|----------------|-------------------------|
| Language       | Python 3.10+            |
| Agent framework| LangGraph + LangChain   |
| Local LLM      | Ollama – qwen2.5:3b     |
| Tool protocol  | MCP (Model Context Protocol) |
| Knowledge base | JSON                    |
| Memory / tickets | SQLite                |
| CLI UI         | Rich                    |

No paid/cloud LLM APIs are used.

---

## 4. Installation

```bash
cd ai_it_helpdesk
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 5. Ollama Setup

1. Install Ollama from https://ollama.com
2. Start the Ollama service
3. Pull the model:

```bash
ollama pull qwen2.5:3b
```

Verify:

```bash
ollama list
```

---

## 6. Running the Project

**Interactive mode**

```bash
python agent_client.py
```

**Demo mode** (runs 3 example problems automatically)

```bash
python agent_client.py --demo
```

**MCP server** (optional, can be inspected or used by other MCP clients)

```bash
python mcp_server.py
```

---

## 7. Demo Commands

```bash
python agent_client.py --demo
```

The demo runs:

1. “My Wi-Fi is not connecting.”
2. “My computer is running very slowly.”
3. “I cannot log in to my account.”

---

## 8. Example Queries

- My Wi-Fi is not connecting.
- Internet is very slow today.
- I forgot my password.
- Printer is offline.
- Computer is extremely slow.
- VPN keeps disconnecting.
- Cannot send emails from Outlook.
- Software installation failed.
- Nothing worked. Please create a support ticket.
- Show me system information.

---

## 9. MCP Tools

| Tool                        | Purpose                                      |
|-----------------------------|----------------------------------------------|
| `search_knowledge_base_tool`| Search local IT knowledge base               |
| `diagnose_issue`            | Analyze problem → causes + steps             |
| `get_system_info`           | Basic OS / hostname / Python info            |
| `create_support_ticket`     | Create ticket in SQLite and return ticket ID |

Tools are defined in `mcp_server.py` using the official MCP Python SDK (`FastMCP`).

---

## 10. Project Structure

```
ai_it_helpdesk/
├── agent_client.py      # LangGraph agent + Rich CLI
├── mcp_server.py        # MCP server exposing the 4 tools
├── database.py          # SQLite (conversations + tickets)
├── knowledge_base.py    # JSON knowledge-base search
├── requirements.txt
├── README.md
├── PROJECT_REPORT.md
└── data/
    ├── helpdesk_kb.json # 16 IT support entries
    └── helpdesk.db      # created automatically
```

---

## Notes

- Conversation history and support tickets are stored locally in SQLite.
- If Ollama is not running or the model is missing, a clear error message is shown.
- The project is intentionally kept simple so a student can explain every part in a viva.
