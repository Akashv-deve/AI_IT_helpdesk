Markdown# AI IT Helpdesk Agent

A local-first agentic IT helpdesk that routes technical issues, retrieves troubleshooting guidance, escalates low-confidence cases, and persists support tickets using **LangGraph, Ollama, MCP, Streamlit, and SQLite**.

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
It also demonstrates persistent ticket history, the MCP stdio handshake, dashboard monitoring, and the deterministic offline fallback.OverviewAI IT Helpdesk Agent is a local support system for common technical issues such as Wi-Fi, printers, VPN, login problems, software issues, and slow computers.Instead of blindly generating an answer, the system evaluates the knowledge-base match after tool execution. When the result is below the configured confidence threshold, it creates a support ticket and informs the user that the issue has been escalated.The application can run with a local Ollama model or fall back to a deterministic rule-based reasoner when Ollama is unavailable.Why I Built ThisA simple IT chatbot can produce an answer even when it has little evidence that the answer is relevant. This project explores a safer workflow:PlaintextNatural-language issue
        ↓
Tool selection
        ↓
Knowledge / diagnostic tool
        ↓
Retrieval confidence
        ↓
Answer OR human escalation
        ↓
Persistent ticket / conversation record
The focus is on practical agent engineering rather than a chat interface alone.Key FeaturesAgentic WorkflowLangGraph state-machine orchestrationTool routing from natural-language queriesConditional branching based on retrieval confidenceAutomatic escalation of low-confidence issuesPersistent conversation and ticket recordsLocal AIOllama-powered local reasoningqwen2.5:3b modelNo paid cloud API requiredDeterministic rule-based fallback when Ollama is unavailableToolingFour core tools are implemented:ToolPurposesearch_knowledge_baseSearch the local IT knowledge basediagnose_issueAnalyse an issue and return likely causes and stepsget_system_infoRetrieve basic local system informationcreate_support_ticketCreate a support ticket in SQLiteMCP IntegrationThe same tool implementations are also exposed through a real Model Context Protocol (MCP) server over stdio.The normal LangGraph agent uses the shared Python implementations in-process. The MCP interface can be verified independently using the project's MCP client.Bashpython main.py mcp-check
Web ApplicationThe Streamlit interface includes:HelpdeskTicketsHistoryKnowledge BaseDashboardDiagnosticsCLIThe project also provides a Rich-based command-line interface for:Bashpython main.py
python main.py ask "my wifi keeps dropping" -v
python main.py demo
python main.py tickets --status open
python main.py history
python main.py doctor
python main.py mcp-check
ScreenshotsHelpdeskConfidence-Based EscalationTicket ManagementDashboardDiagnosticsArchitecturePlaintext                         ┌──────────────────┐
                         │    User Query    │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │      route       │
                         │ Tool selection   │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │     execute      │
                         │   Tool call     │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │    Confidence    │
                         │      Check       │
                         └───────┬───┬──────┘
                                 │   │
                      high ──────┘   └────── low
                       │                     │
                       ▼                     ▼
                ┌─────────────┐      ┌───────────────┐
                │   respond   │      │ create ticket │
                └──────┬──────┘      └───────┬───────┘
                       │                     │
                       └──────────┬──────────┘
                                  ▼
                         ┌──────────────────┐
                         │   Final Answer   │
                         └──────────────────┘

       Ollama ───────────────► Local reasoning
       RuleBasedReasoner ─────► Offline fallback
       JSON KB ───────────────► Retrieval
       SQLite ────────────────► History + tickets
       MCP Server ────────────► External tool interface
Confidence-Based EscalationThe central reliability mechanism is the confidence gate. When a tool produces a weak knowledge-base match, the graph does not continue directly to a generated troubleshooting answer.Instead:PlaintextLow retrieval confidence
        ↓
create_support_ticket
        ↓
Persist ticket in SQLite
        ↓
Return deterministic escalation response
The user receives the generated ticket ID and can track the issue through the Tickets interface. The confidence value is a knowledge-base retrieval score, not a calibrated probability.Knowledge BaseThe project includes a local JSON knowledge base containing 16 curated IT support articles covering areas such as:Wi-FiInternet connectivityLogin and passwordsPrintersSlow computersVPNEmailSoftwareKeyboard and mouseBrowsersWindows system issuesLocation: data/helpdesk_kb.jsonThe retrieval implementation uses transparent keyword-based scoring so results can be inspected and explained without requiring a vector database.Technology StackTechnologyPurposePythonCore implementationLangGraphAgent orchestrationOllamaLocal LLM runtimeQwen2.5 3BLocal reasoning modelMCPTool protocolStreamlitWeb interfaceRichCLISQLitePersistent storageJSONKnowledge basepytestAutomated testingStreamlit AppTestUI testingRuffLintingGitHub ActionsContinuous integrationInstallation1. Clone the repositoryBashgit clone [https://github.com/Akashv-deve/AI_IT_helpdesk.git](https://github.com/Akashv-deve/AI_IT_helpdesk.git)
cd AI_IT_helpdesk
2. Create a virtual environmentBashpython -m venv .venv
.\.venv\Scripts\Activate.ps1
(If PowerShell blocks activation:)BashSet-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
3. Install dependenciesBashpython -m pip install --upgrade pip
pip install -r requirements.txt
(For development and testing:)Bashpip install -r requirements-dev.txt
4. Enable local AI reasoningInstall Ollama and pull the configured model:Bashollama pull qwen2.5:3b
Ollama is optional. Without it, the application uses the deterministic fallback reasoner.Running the ApplicationWeb InterfaceBashstreamlit run app.py
Open: http://localhost:8501CLIBashpython main.py
Health CheckBashpython main.py doctor
MCP VerificationBashpython main.py mcp-check
Offline ModeTo run a deterministic demonstration without Ollama:PowerShell$env:HELPDESK_OFFLINE = "1"
streamlit run app.py
The web UI also provides a "Force offline mode" option.TestingThe repository contains 115 automated tests covering:knowledge-base retrievalagent routing and escalationSQLite persistencetool contractsMCP server behaviourservice-layer validationStreamlit pages and user flowsRun the complete test suite:Bashpytest
Run linting:Bashruff check src tests main.py app.py
GitHub Actions runs the test and lint workflow automatically.Placement Demo FlowA short placement demonstration can show:Known IT issueTool selection + retrieval confidenceUnsupported issueAutomatic escalationTicket createdTicket workflowConversation historyDashboardMCP handshakeOffline fallbackThe goal is to demonstrate the complete system rather than only the chat UI.Project StructurePlaintextAI_IT_helpdesk/
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
├── demo/
│   └── AI_IT_Helpdesk_Demo.mp4
├── .env.example
├── .github/
├── .streamlit/
├── .vscode/
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
LimitationsRetrieval uses transparent keyword-based scoring, so heavily paraphrased issues may produce weaker matches.The knowledge base currently contains 16 curated articles.Conversation history is persisted, but previous turns are not currently fed back into the agent as conversational context.The application is designed for local use and demonstration rather than multi-user production deployment.The retrieval confidence value is a match score, not a calibrated probability.DocumentationArchitectureProject ReportAuthorAkash VBuilt as a portfolio project to explore practical local AI agents, tool orchestration, reliability-aware escalation, and developer-focused AI systems.LicenseMIT License — see LICENSE.
