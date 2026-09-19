# PROJECT REPORT

## AI IT Helpdesk Agent

**A Local-First Agentic AI System for Automated IT Support**

---

## 1. Project Title

**AI IT Helpdesk Agent**

---

## 2. Problem Statement

Users frequently encounter common IT problems such as:

- Wi-Fi connectivity issues
- Internet problems
- Login and password problems
- Printer failures
- Slow computers
- VPN issues
- Email problems
- Software installation and application issues
- Browser problems
- Windows system issues

Many helpdesk requests are repetitive, but a simple chatbot is not enough for
reliable support. A system that always generates an answer can produce a
confident-looking response even when the available knowledge is not relevant.

This project addresses that problem with a structured agent workflow that can:

1. Accept a problem in natural language.
2. Select an appropriate support tool.
3. Retrieve or diagnose the issue using local resources.
4. Evaluate the knowledge-base retrieval confidence.
5. Provide a response when the evidence is sufficient.
6. Escalate low-confidence issues by creating a support ticket.
7. Persist conversations and tickets in SQLite.
8. Continue operating with a deterministic fallback when Ollama is unavailable.

---

## 3. Project Overview

AI IT Helpdesk Agent is a **local-first agentic IT support application** built
with:

- **Python**
- **LangGraph**
- **Ollama with Qwen2.5 3B**
- **Model Context Protocol (MCP)**
- **Streamlit**
- **Rich**
- **SQLite**
- **JSON knowledge base**

The project is designed so that the normal agent path uses shared Python tool
implementations in-process, while the same tools are also exposed through a
separate MCP stdio server.

No paid cloud API is required for the core application.

The application provides both a web interface and CLI, along with automated
tests, diagnostics, MCP verification, and a deterministic offline mode.

---

## 4. Objectives

The main objectives of the project are:

1. Build a genuine agentic workflow instead of a fixed sequence of hard-coded
   responses.
2. Use a local LLM through Ollama for routing and response generation.
3. Route natural-language IT problems to appropriate tools.
4. Use a transparent knowledge-base retrieval score to decide whether the
   result is strong enough to answer automatically.
5. Escalate low-confidence cases into support tickets rather than generating
   unsupported troubleshooting guidance.
6. Persist conversations and tickets using SQLite.
7. Expose the same tools through the Model Context Protocol (MCP).
8. Provide a deterministic fallback so the application remains usable without
   Ollama.
9. Provide a Streamlit interface suitable for demonstration.
10. Maintain a testable, lightweight codebase suitable for technical review and
    placement interviews.

---

## 5. Proposed Solution

The system processes each helpdesk request through a structured LangGraph
workflow:

```text
User Query
    ↓
route
    ↓
execute
    ↓
Confidence Check
    ├── High confidence → respond
    └── Low confidence  → create support ticket → respond
```

The workflow separates decision-making, tool execution, confidence evaluation,
escalation, and final response handling.

This creates an explicit reliability boundary: a weak retrieval result can
lead to human escalation instead of an unsupported answer.

---

## 6. System Architecture

### 6.1 High-Level Architecture

```text
                         ┌──────────────────┐
                         │    User Query    │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │      route       │
                         │  Select a tool   │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │     execute      │
                         │    Run tool      │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Confidence Check │
                         └───────┬─────┬────┘
                                 │     │
                              high     low
                                 │     │
                                 ▼     ▼
                           ┌────────┐ ┌──────────────┐
                           │ respond│ │ create ticket│
                           └────┬───┘ └──────┬───────┘
                                │            │
                                └─────┬──────┘
                                      ▼
                              ┌──────────────┐
                              │ Final Answer │
                              └──────────────┘
```

Supporting components:

```text
Ollama ───────────────► Local reasoning
RuleBasedReasoner ────► Deterministic fallback
JSON knowledge base ──► Retrieval
SQLite ────────────────► Conversations + tickets
MCP server ────────────► Tool protocol interface
Streamlit ─────────────► Web presentation
Rich CLI ──────────────► Terminal interface
```

### 6.2 LangGraph Workflow

The graph is implemented with four primary nodes:

| Node | Responsibility |
|---|---|
| `route` | Select the most appropriate support tool |
| `execute` | Run the selected tool and collect its result |
| `escalate` | Create a support ticket when the confidence gate fires |
| `respond` | Produce the final user-facing response |

The graph contains a conditional edge after tool execution.

```text
route
  ↓
execute
  ↓
confidence check
 ├── high confidence → respond
 └── low confidence → escalate → respond
```

The escalation path is especially important because it prevents the system from
treating every retrieved result as equally trustworthy.

---

## 7. Retrieval and Confidence

The knowledge base is stored in:

```text
data/helpdesk_kb.json
```

It currently contains **16 curated IT support articles** across multiple
categories.

Retrieval is based on transparent keyword-overlap scoring rather than an
embedding model.

The scoring combines multiple signals, including:

- meaningful query-word coverage
- title overlap
- category overlap
- symptom overlap

Conceptually:

```python
score = (
    0.45 * coverage
    + 0.20 * title_hit
    + 0.20 * category_hit
    + 0.15 * symptom_hit
)
```

The score is bounded to the range `[0, 1]` and is used as a
**knowledge-base retrieval/match score**.

It is not a calibrated probability.

### Why transparent retrieval?

A keyword-based scorer keeps the mechanism:

- lightweight
- easy to inspect
- explainable during an interview
- independent of an additional embedding model
- deterministic in tests

The trade-off is that heavily paraphrased requests may produce weaker matches.
That is treated as a known limitation rather than hidden from the user.

### Weak-match handling

Weak matches are filtered relative to the best result so that a low-quality
article does not unnecessarily enter the response context.

When no useful result remains, retrieval returns an empty result. This enables
the confidence gate to escalate instead of forcing the system to answer from an
irrelevant article.

---

## 8. Tool Design

The four core tools are defined in:

```text
src/helpdesk/tools.py
```

Each tool returns a `ToolResult` containing both user-readable information and
execution metadata.

Conceptually:

```python
@dataclass(frozen=True)
class ToolResult:
    text: str
    confidence: float = 0.0
    ok: bool = True
    metadata: dict = ...
```

### 8.1 `search_knowledge_base`

Searches the local JSON knowledge base for relevant troubleshooting guidance.

### 8.2 `diagnose_issue`

Analyses a reported issue and returns likely causes and recommended steps.

### 8.3 `get_system_info`

Returns basic local machine information used by the helpdesk diagnostics.

### 8.4 `create_support_ticket`

Creates a support ticket in SQLite and returns its ticket ID.

Keeping all four tool implementations in one module provides a single source of
truth for both the local agent and the MCP layer.

---

## 9. Reasoning Layer

The reasoning abstraction is implemented in:

```text
src/helpdesk/llm.py
```

It defines a common `Reasoner` interface with two operations:

```python
route(query)
synthesize(query, result)
```

There are two implementations.

| Reasoner | Used when |
|---|---|
| `OllamaReasoner` | Ollama is reachable and the configured model is available |
| `RuleBasedReasoner` | Ollama is unavailable or offline mode is enabled |

### 9.1 Ollama Reasoner

The application uses:

```text
Ollama
qwen2.5:3b
```

The local model performs tool routing and normal response synthesis.

The model is accessed through the LangChain Ollama integration.

### 9.2 Deterministic Fallback

When Ollama is unavailable, the application falls back to a deterministic
keyword-based reasoner.

This provides several practical benefits:

- the application remains demonstrable without a model server
- automated tests do not require Ollama
- CI can run without GPU access
- the system degrades instead of becoming unusable when the local model is
  unavailable

The graph does not need separate architecture for these modes because both
reasoners implement the same interface.

---

## 10. Confidence-Based Escalation

The confidence gate is the central reliability feature.

For a high-confidence knowledge-base match:

```text
Tool Result
    ↓
Confidence ≥ threshold
    ↓
Generate normal response
```

For a low-confidence match:

```text
Tool Result
    ↓
Confidence < threshold
    ↓
create_support_ticket
    ↓
Persist ticket in SQLite
    ↓
Return deterministic escalation response
```

The resulting response includes the ticket ID so the user can reference the
issue later.

The current default escalation threshold is exposed through configuration and
shown in the web UI.

---

## 11. Escalation Response Safety

A low-confidence request should not continue into normal LLM synthesis, because
the local model may otherwise generate plausible but unsupported troubleshooting
steps for an issue that is not represented in the knowledge base.

The escalation path therefore produces a deterministic response containing:

- the fact that no reliable knowledge-base match was found
- the fact that the issue was escalated
- the generated ticket ID
- a short follow-up instruction

This keeps the escalation branch consistent with the project's design goal:
**do not invent a solution when evidence is insufficient.**

---

## 12. MCP Integration

The project exposes the four tools through a real
**Model Context Protocol (MCP)** server over stdio.

The MCP implementation is located in:

```text
src/helpdesk/mcp_server.py
```

The local client is implemented in:

```text
src/helpdesk/mcp_client.py
```

### Architecture

The normal LangGraph agent uses the shared Python tool implementations
directly in-process.

Separately:

```text
Shared Tool Implementations
        ├──► LangGraph agent
        └──► MCP stdio server
```

The MCP server can therefore be verified independently without making MCP the
transport for every normal agent execution.

### MCP verification

The project provides:

```powershell
python main.py mcp-check
```

This starts the MCP server over stdio, completes the protocol handshake, lists
the advertised tools, and verifies the interface.

---

## 13. Persistence

The application uses SQLite for local persistence.

The database stores two main categories of information:

### Conversations

Each handled turn records information such as:

- user query
- route reason
- selected tool
- tool result
- final response
- retrieval confidence
- escalation state
- reasoning mode
- timestamp

### Support Tickets

Tickets store:

- ticket ID
- original user query
- recorded description
- status
- creation timestamp

The runtime database is:

```text
data/helpdesk.db
```

The database is intentionally treated as runtime data and is excluded from
version control.

---

## 14. Service Layer

The service layer is implemented in:

```text
src/helpdesk/service.py
```

It sits between the presentation layer and the agent.

Its responsibilities include:

- input validation
- coordinating agent execution
- returning structured turn results
- exposing ticket and history operations
- providing dashboard statistics
- providing health checks
- containing internal errors so UI users do not see raw tracebacks

Both the CLI diagnostics and Streamlit Diagnostics page use the same service
health-check logic.

---

## 15. Web Application

The Streamlit application is launched using:

```powershell
streamlit run app.py
```

The web layer is located under:

```text
src/web/
```

The application provides six pages:

1. **Helpdesk** — primary conversational interface
2. **Tickets** — support ticket listing and status updates
3. **History** — persisted conversation records
4. **Knowledge Base** — local support knowledge
5. **Dashboard** — operational metrics and runtime state
6. **Diagnostics** — environment checks and MCP verification

The sidebar also provides:

- Ollama AI mode indicator
- Force offline mode
- Show agent details
- model and escalation information
- conversation clearing

The UI displays execution facts such as:

- selected tool
- routing reason
- retrieval confidence
- escalation state
- reasoning mode

It does not expose hidden model chain-of-thought.

---

## 16. Command-Line Interface

The project also provides a Rich-powered CLI.

Interactive mode:

```powershell
python main.py
```

Example commands include:

```powershell
python main.py ask "my wifi keeps dropping" -v
python main.py demo
python main.py tickets --status open
python main.py history
python main.py doctor
python main.py mcp-check
```

The CLI and Streamlit application operate over the same underlying service,
agent, tool, and database layers.

---

## 17. Configuration

Configuration is handled through:

```text
src/helpdesk/config.py
```

The example configuration is provided in:

```text
.env.example
```

Relevant configuration includes:

```text
OLLAMA_MODEL
OLLAMA_BASE_URL
LLM_TEMPERATURE
LLM_MAX_TOKENS
KB_PATH
DB_PATH
KB_TOP_K
ESCALATION_THRESHOLD
HELPDESK_OFFLINE
```

This avoids embedding environment-specific settings throughout the source
code.

---

## 18. Testing Strategy

The repository contains **115 automated tests**.

The tests cover multiple layers of the application.

| Test area | Focus |
|---|---|
| Knowledge base | ranking, weak matches, empty results, score behaviour |
| Database | persistence, rollback, timestamps, ticket IDs |
| Tools | tool contracts, dispatch, failure handling, escalation |
| Graph | routing, confidence branching, escalation, persistence |
| MCP | tool advertisement and MCP server behaviour |
| Service | validation, tickets, history, dashboard, health |
| Web | Streamlit pages and user flows |

The Streamlit tests use `AppTest` so UI flows can be exercised programmatically.

The deterministic reasoner allows the suite to run without requiring Ollama.

Run all tests with:

```powershell
pytest
```

Run linting with:

```powershell
ruff check src tests main.py app.py
```

GitHub Actions provides continuous integration for the repository.

---

## 19. Demonstration Workflow

The project is designed for a short placement demonstration.

### Known issue

Example:

```text
Wi-Fi keeps disconnecting
```

The agent routes to an appropriate tool, retrieves a strong knowledge-base
match, and generates a troubleshooting response.

### Low-confidence issue

Example:

```text
My quantum flux capacitor is misaligned
```

The request does not have a useful knowledge-base match.

The system:

1. Produces a low retrieval confidence result.
2. Triggers the confidence gate.
3. Creates a support ticket.
4. Returns a deterministic escalation response.
5. Displays the ticket ID.
6. Persists the event in SQLite.

### Operational verification

The demonstration can then open:

- Tickets
- History
- Dashboard
- Diagnostics

and run the MCP handshake.

### Offline mode

The **Force offline mode** option can be enabled to demonstrate that the
application still performs deterministic routing and keeps its retrieval,
ticketing, and persistence functionality without an LLM.

---

## 20. User Interface Screenshots

The repository includes screenshots covering:

```text
screenshots/
├── helpdesk.png
├── escalation.png
├── tickets.png
├── dashboard.png
└── diagnostics.png
```

These screenshots document the major user-visible workflows.

---

## 21. Implementation Structure

```text
AI_IT_helpdesk/
├── app.py
├── main.py
├── data/
│   └── helpdesk_kb.json
├── screenshots/
│   ├── helpdesk.png
│   ├── escalation.png
│   ├── tickets.png
│   ├── dashboard.png
│   └── diagnostics.png
├── demo/
│   └── AI_IT_Helpdesk_Demo.mp4
├── docs/
│   ├── ARCHITECTURE.md
│   └── PROJECT_REPORT.md
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
```

---

## 22. Security and Reliability Considerations

The project is designed around several practical reliability principles:

### Local processing

The configured model runs through Ollama on the local machine, so the core
reasoning workflow does not require a paid hosted LLM API.

### Deterministic fallback

A rule-based implementation provides predictable behaviour when Ollama is
unavailable.

### Confidence gate

A weak knowledge-base match can trigger human escalation rather than forcing
an automatic answer.

### Controlled persistence

SQLite provides a small local persistence layer without requiring a separate
database service.

### Explainable execution metadata

The web UI can show the selected tool, routing reason, retrieval score,
escalation state, and reasoning mode.

These mechanisms improve observability and predictable behaviour, but they do
not constitute a complete enterprise security system.

---

## 23. Challenges and Engineering Decisions

### 23.1 Small local model behaviour

A 3B local model has fewer capabilities than a much larger hosted model.
Prompts, structured routing output, parsing safeguards, and a deterministic
fallback are therefore important.

### 23.2 Reliable escalation

Returning the highest-scoring article regardless of score would make out-of-
scope questions appear supported. The project instead treats a weak or empty
retrieval result as a reason to escalate.

### 23.3 MCP compatibility

The MCP SDK has changed server imports across major versions. The project
contains a compatibility import layer so the server can support the configured
dependency range.

### 23.4 Testability

The service layer and deterministic reasoner reduce the amount of environment
state required by tests and make it possible to validate the graph without
requiring a live LLM.

### 23.5 Keeping the project lightweight

The architecture intentionally avoids introducing a vector database, cloud
API, distributed deployment system, or heavyweight infrastructure for the
current scope.

---

## 24. Limitations

1. Retrieval uses keyword-based scoring, so heavily paraphrased issues may
   produce weaker matches.
2. The current knowledge base contains 16 curated articles.
3. Conversation history is persisted, but previous turns are not currently fed
   back into the agent as conversational context.
4. The local Qwen2.5 3B model has less capacity than much larger models.
5. The application is designed for local use and demonstration rather than
   multi-user production deployment.
6. The retrieval confidence value is a knowledge-base match score, not a
   calibrated probability.
7. The current project does not provide enterprise authentication or a
   distributed ticketing backend.

---

## 25. Future Enhancements

Possible future improvements include:

- richer retrieval for larger knowledge bases
- multi-turn conversational context
- additional helpdesk tools
- integration with external ticketing platforms
- broader system diagnostics
- stronger observability
- enterprise authentication
- packaging and deployment options for multi-user environments

These are outside the scope of the current lightweight implementation.

---

## 26. Conclusion

The AI IT Helpdesk Agent demonstrates a practical local-first agent architecture
for IT support.

The system combines:

- natural-language routing
- tool execution
- transparent retrieval scoring
- confidence-based escalation
- local LLM reasoning
- deterministic fallback
- MCP tool exposure
- SQLite persistence
- Streamlit presentation
- CLI access
- automated testing and CI

The most important design decision is the separation between **answering with
sufficient evidence** and **escalating when evidence is insufficient**.

This makes the project useful as a demonstration of practical Agentic AI
engineering rather than a simple question-and-answer chatbot.

---

## 27. References

1. LangGraph — https://langchain-ai.github.io/langgraph/
2. LangChain Ollama integration — https://python.langchain.com/docs/integrations/chat/ollama/
3. Model Context Protocol — https://modelcontextprotocol.io/
4. Ollama — https://ollama.com/
5. Qwen2.5 — https://huggingface.co/Qwen/Qwen2.5-3B
6. Rich — https://rich.readthedocs.io/
7. SQLite — https://www.sqlite.org/
8. Streamlit — https://streamlit.io/
