# Architecture


This document explains *why* the system is built the way it is. It is written
to answer the questions an interviewer or examiner is most likely to ask.

---

## 1. The control flow

```
                  ┌──────────────────────────────┐
   user query ───▶│ route                        │
                  │ reasoner picks one tool      │
                  └──────────────┬───────────────┘
                                 ▼
                  ┌──────────────────────────────┐
                  │ execute                      │
                  │ run the tool, get text +     │
                  │ a confidence score           │
                  └──────────────┬───────────────┘
                                 │
                 confidence ≥ threshold │ confidence < threshold
                    ┌────────────┘      └────────────┐
                    ▼                                ▼
         ┌────────────────────┐          ┌────────────────────────┐
         │ respond            │◀─────────│ escalate               │
         │ write the answer   │          │ create a support ticket│
         └─────────┬──────────┘          └────────────────────────┘
                   ▼
        answer to user + SQLite record
```

Four nodes, one conditional edge. The graph is defined in `graph.py` and
compiled once per process.

### Why a graph at all?

A straight `route → execute → respond` chain would be a pipeline, and a
pipeline does not need LangGraph — a function would do. The conditional edge
out of `execute` is what earns the framework: the agent inspects its own
output and changes its plan. That is the difference between automation and
agency, and it is the thing worth defending in a viva.

### Why escalate on low confidence?

A helpdesk exists to resolve problems, and a wrong-but-fluent answer costs more
than no answer: the user follows five useless steps, loses twenty minutes, and
*then* files a ticket anyway. Refusing to guess is the correct product
behaviour, and it is cheap to implement once retrieval returns a score rather
than just text.

---

## 2. Retrieval and the confidence score

`knowledge_base.search()` scores every article against the query and returns
hits sorted by confidence. Four weighted signals combine to a value in `[0, 1]`:

```python
score = 0.45 * coverage      # fraction of the query's meaningful words explained
      + 0.20 * title_hit     # overlap with the article title
      + 0.20 * category_hit  # the query names a category: "vpn", "printer"
      + 0.15 * symptom_hit   # overlap with curated symptom phrases
```

Preprocessing: lowercase, strip inner hyphens so `Wi-Fi` becomes one token
(otherwise it splits into `wi` and `fi`, both too short to survive), split on
non-alphanumerics, drop stopwords and tokens of two characters or fewer.

**Keyword scoring, not embeddings.** Embeddings would handle paraphrase better,
but they add a model download, a vector index and a second inference step — and
the score becomes a cosine distance nobody can explain. Since this score gates
whether a human gets pulled in, being able to justify it line by line is worth
more than the recall improvement. The trade-off is documented as a known
limitation rather than hidden.

**Weak matches are dropped.** After sorting, any hit scoring below half the
best match is discarded. Without this, "I forgot my password" returned the
password article at 90%, the login article at 60%, *and* a Wi-Fi article at
22% — noise that goes straight into the LLM prompt and onto the user's screen.
Returning one good answer beats returning three of mixed quality.

**A miss returns an empty list.** The obvious shortcut — return the
highest-scoring article no matter how low the score — makes the system
confidently wrong on every out-of-scope question. Returning nothing is what
lets the graph escalate.

---

## 3. Tool design

All four tools live in `tools.py` and return a `ToolResult`:

```python
@dataclass(frozen=True)
class ToolResult:
    text: str                    # what a human reads
    confidence: float = 0.0      # what the graph routes on
    ok: bool = True              # did the tool itself succeed
    metadata: dict = ...         # matched titles, ticket id, ...
```

MCP tools must return a plain string, so `mcp_server.py` wraps each function
and hands back `.text`. The agent, running in-process, gets the whole object
including the confidence it needs for routing.

This is the fix for the most serious flaw in the original version, where the
tool logic was copy-pasted into both `agent_client.py` and `mcp_server.py`.
Two copies of the same logic drift apart the moment one is edited, and the
duplication also meant the MCP server was decorative — the agent never called
it.

`run_tool()` converts every failure into a `ToolResult(ok=False)`. A tool can
never crash the agent loop; a failed tool becomes a low-confidence result,
which routes to escalation, which is exactly right.

---

## 4. The reasoning layer

`llm.py` defines an interface with two methods and two implementations:

```python
class Reasoner(ABC):
    def route(self, query) -> tuple[str, str]: ...
    def synthesize(self, query, result) -> str: ...
```

| Implementation | Used when |
|---|---|
| `OllamaReasoner` | Ollama is reachable and the model is pulled |
| `RuleBasedReasoner` | Ollama is missing, or `--offline` / `HELPDESK_OFFLINE=1` |

`get_reasoner()` picks one, probes it, and caches the result for the process
lifetime.

**Why the fallback exists.** Three reasons, in order of importance: CI has no
GPU and no Ollama, so the test suite would otherwise be unrunnable; anyone
cloning the repo can see it work before committing to a 2 GB download; and the
agent degrades rather than crashes if the model server dies mid-session.

**Why caching matters.** The original code called `get_llm()` inside every
graph node, and each call constructed a fresh client *and* sent a health-check
prompt. A single user turn therefore paid for six model invocations where two
were needed. Building it once cuts latency by roughly two thirds.

**Parsing small-model output.** A 3B model asked for JSON will often wrap it in
markdown fences or precede it with "Sure! Here you go:". `_extract_json()`
strips fences, then finds the first `{...}` block, and falls back to rule-based
routing if it still cannot parse. Tests cover all three shapes.

---

## 5. Persistence

Two tables: `conversations` (every turn, with the tool chosen, the confidence
and whether it escalated) and `support_tickets`.

Three details worth pointing at:

- **No import-time side effects.** The original module called `init_db()` at
  the bottom of the file, so merely importing it created a database. Entry
  points now call `init_db()` explicitly.
- **Context-managed connections.** `connect()` commits on success, rolls back
  on exception and always closes. Tested with a deliberate failure.
- **Timezone-aware timestamps.** `datetime.utcnow()` is deprecated in Python
  3.12 and returns a *naive* datetime that compares incorrectly against aware
  ones. The code uses `datetime.now(timezone.utc)`.

Ticket IDs combine a UTC timestamp with a four-character random suffix. The
original used the timestamp alone with an exception handler for collisions;
a test creating 50 tickets in one second demonstrates why the suffix is needed.

---

## 6. MCP integration

`mcp_server.py` exposes the four tools over stdio. The import shim at the top
handles both major versions of the SDK:

```python
try:                                          # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ModuleNotFoundError:                   # mcp < 2.0
    from mcp.server.fastmcp import FastMCP as _Server
```

FastMCP was renamed to MCPServer in mcp 2.0. A single hard-coded import means
the project breaks for everyone on the other side of that boundary — a real
risk when `requirements.txt` says `mcp>=1.0`.

Status messages go to **stderr**, never stdout: stdout is the protocol channel
and a stray `print()` corrupts the JSON-RPC stream.

`mcp_client.py` plus `python main.py mcp-check` exist to make the MCP layer
falsifiable. It spawns the server as a subprocess, completes the handshake,
lists the advertised tools and invokes one, printing the result. "This project
uses MCP" is a claim; that command is the evidence.

---

## 6b. The service layer and the web UI

``service.py`` sits between any user interface and the agent. It exists for two
reasons:

* **Testability.** Every UI behaviour — repeated queries, escalation, empty
  input, Ollama being down — is asserted without rendering a widget.
* **Error containment.** ``HelpdeskService.ask()`` never raises. Invalid input
  and internal failures come back as a ``TurnResult`` with ``error`` set, so a
  helpdesk user never sees a traceback.

``doctor`` on the CLI and the Diagnostics page in the browser both call
``service.health()``, so the two can never disagree.

``src/web`` holds presentation only: an application shell (page config, sidebar,
``st.navigation``), a session-state module, a small stylesheet, and six page
modules. No page imports ``graph.py`` or ``database.py`` directly.

Two details specific to Streamlit:

* The service is cached with ``@st.cache_resource``, not ``cache_data`` — it
  holds a compiled LangGraph and a live model client, which must not be
  serialised between reruns.
* Every page function is named ``render``, so Streamlit would infer the same URL
  pathname for all six. ``st.Page(..., url_path=...)`` is set explicitly. This
  was caught by ``AppTest``, not by an HTTP check: the server returned 200 while
  the script itself raised.

## 7. Configuration

`config.py` loads a `.env` file and exposes one shared `Settings` instance.
It is deliberately mutable: every module imports the same object, so a test can
redirect `db_path` on it and the whole application follows, without threading a
config parameter through every function signature.

---

## 8. Testing strategy

| File | Focus |
|---|---|
| `test_knowledge_base.py` | Ranking correctness, empty results on a miss, weak-match filtering, bounded scores |
| `test_database.py` | Round-trips, ID uniqueness under load, rollback, tz-aware timestamps |
| `test_tools.py` | Each tool's contract, dispatch, failure handling, escalation rule |
| `test_graph.py` | Both branches of the conditional edge, no double-ticketing, persistence |
| `test_mcp_server.py` | The MCP surface matches the tool registry exactly |
| `test_service.py` | Input validation, escalation, tickets, history, dashboard, health |
| `test_web.py` | Real Streamlit renders via `AppTest` — every page, the full chat flow |

Every test runs against a temporary SQLite file and the deterministic reasoner,
so the suite is fast, hermetic and needs no model server.

The tests that matter most are the negative ones: `search()` returning empty on
nonsense, escalation firing, and an explicit ticket request *not* producing two
tickets.

---

## 9. What was changed from the first version

| Problem | Fix |
|---|---|
| Tool logic duplicated in the agent and the MCP server | Single `tools.py`, imported by both |
| The agent never actually spoke MCP | `mcp_client.py` and `mcp-check` do a real stdio round-trip |
| LLM rebuilt with a health-check ping on every node | Cached singleton, probed once |
| Unmatched query silently returned article #1 | Empty result, then escalation |
| Weak matches padded out good answers | Relative relevance floor at 50% of the best hit |
| Linear graph — LangGraph added nothing | Conditional edge on confidence |
| `datetime.utcnow()` (deprecated, naive) | `datetime.now(timezone.utc)` |
| `init_db()` ran on import | Explicit call from entry points |
| Connections leaked on exceptions | Context manager with rollback |
| Ticket IDs collided within a second | Timestamp + random suffix, tested |
| Model, paths, thresholds hard-coded | `config.py` + `.env` |
| `__pycache__/` and `helpdesk.db` committed | `.gitignore` |
| No tests, no CI, no lint | pytest suite, GitHub Actions, ruff |
| Unusable without Ollama | Rule-based fallback |
| CLI-only; nothing to show a non-technical viewer | Six-page Streamlit app over the same engine |
| UI would have had to call `graph.py` directly | `service.py` façade with validation and error containment |
| Tool metadata was dropped before synthesis, so answers opened with a generic "Here is what I found" | `tool_metadata` carried through the graph state |
| Blank input recorded an error turn in the transcript | Guarded at the page, still validated in the service |
| `get_reasoner` cache held one entry, so the two modes evicted each other | `maxsize=2` |
