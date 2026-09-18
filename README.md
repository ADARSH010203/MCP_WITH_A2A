# MCP + A2A Multi-Agent System

A modular Python multi-agent system that combines **Agent-to-Agent (A2A)** communication with the **Model Context Protocol (MCP)**.

The system accepts a user request, routes it to a specialized agent, and uses MCP when a request needs an external tool. The current MCP example uses a daily reference-rate currency provider through an MCP tool.

## Architecture

```text
User
  |
  v
Host / Client
  |
  v
A2A Server
  |
  v
Multi-Agent Router
  |
  +--> Currency Agent ------> MCP Server ------> Currency Tool
  +--> Email Agent
  +--> Code Agent
  +--> Image Agent
  +--> Game Agent
  +--> Deep Learning Agent
  +--> Reinforcement Learning Agent
  +--> DSA Agent
```

### Request flow

1. The host sends a task to the A2A JSON-RPC endpoint.
2. The A2A task manager validates the request and creates the task.
3. The router selects a specialized agent using deterministic keyword/phrase matching.
4. The selected agent processes the request with the configured Groq model.
5. Currency requests can call the MCP SSE tool server.
6. The task manager returns the result or streams task updates through SSE.

## Project Structure

```text
MCP_WITH_A2A/
├── app/
│   ├── agents/
│   │   ├── base.py
│   │   ├── currency.py
│   │   ├── email.py
│   │   ├── code.py
│   │   ├── image.py
│   │   ├── game.py
│   │   ├── deep_learning.py
│   │   ├── reinforcement.py
│   │   └── dsa.py
│   ├── a2a/
│   │   ├── server.py
│   │   ├── client.py
│   │   ├── models.py
│   │   ├── base_task_manager.py
│   │   ├── task_manager.py
│   │   ├── card_resolver.py
│   │   ├── push_notification_auth.py
│   │   └── in_memory_cache.py
│   ├── mcp/
│   │   ├── server.py
│   │   └── tools/
│   │       └── currency.py
│   ├── routing/
│   │   └── router.py
│   └── config/
│       ├── constants.py
│       └── settings.py
├── host/
│   ├── host_agent.py
│   ├── google_host_agent.py
│   └── cli.py
├── frontend/
│   └── streamlit_app.py
├── scripts/
│   ├── run_a2a_server.py
│   └── run_mcp_server.py
├── tests/
│   ├── test_router.py
│   └── test_mcp.py
├── .env.example
├── Dockerfile
├── requirements.txt
└── pyproject.toml
```

## Setup

Use Python 3.11+.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\\Scripts\\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local `.env` from `.env.example`:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
MCP_URL=http://127.0.0.1:3000/sse
A2A_TASK_DB_PATH=.data/a2a_tasks.db
```

Never commit a real API key.

## Run the MCP Server

Start MCP first:

```bash
python -m scripts.run_mcp_server
```

The demo SSE endpoint is:

```text
http://127.0.0.1:3000/sse
```

## Run the A2A Server

In another terminal:

```bash
python -m scripts.run_a2a_server --host 127.0.0.1 --port 8000
```

Agent card:

```text
http://127.0.0.1:8000/.well-known/agent.json
```

## Run the Streamlit UI

```bash
streamlit run frontend/streamlit_app.py
```

## Run Tests

The included tests cover routing decisions and the deterministic MCP currency tool without requiring a live Groq request.

```bash
pytest -q
ruff check app host frontend scripts tests
```

## Security and Reliability

- API credentials are loaded from environment variables and should never be committed.
- The A2A client uses request timeouts and validates JSON responses.
- Push-notification URLs are verified before notification configuration is stored.
- Push notifications are signed with RSA-based JWTs and include a request-body digest.
- A2A task state is persisted locally in SQLite by default, while live streaming subscribers remain process-local.
- The router is deterministic and uses word-boundary matching for single-word keywords to reduce accidental matches.
- Duplicate task IDs are idempotent; reusing an ID for a different session or message is rejected.
- Streaming tasks can be canceled while their worker is active.
- Push-notification callback URLs require HTTPS by default and private/loopback destinations are blocked.
- Push notification JWTs include a unique ID and body digest; receivers reject reused tokens within the validity window.
- Currency rates come from a daily reference-rate provider; they are not suitable for live trading or guaranteed settlement prices.

## Limitations

- Currency rates are external daily reference rates and depend on provider availability.
- Agent routing is keyword-based, so ambiguous requests may still be misrouted or fall back to the code agent.
- SQLite persistence protects task records across a single server restart, but it does not provide distributed task state across multiple server processes.
- Live SSE subscriptions and running workers are still process-local; an active task cannot be resumed automatically after a server restart.
- Agent conversation memory is still in-process via LangGraph's memory checkpointer.
- The default agent setup requires a valid Groq API key.
- The current project is a demonstration architecture rather than a production-hardened distributed platform.

## Task Lifecycle

```text
SUBMITTED
   ↓
WORKING
   ├──→ INPUT_REQUIRED
   ├──→ COMPLETED
   ├──→ FAILED
   └──→ CANCELED
```

Tasks with the same ID and the same session/message are treated as retries and do not start a second agent execution. Streaming clients can reconnect to an active in-process worker or replay a terminal task's final state.
## Example Requests

- "What is the exchange rate between USD and EUR?"
- "Write a professional email asking for leave."
- "Create a Python function for binary search."
- "Explain convolutional neural networks."
- "Explain Q-learning."
- "Design a simple game concept."
