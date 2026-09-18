# MCP + A2A Multi-Agent System

A modular Python multi-agent system that combines **Agent-to-Agent (A2A)** communication with the **Model Context Protocol (MCP)**.

The system accepts a user request, routes it to a specialized agent, and uses MCP when a request needs an external tool. The current MCP example is a deterministic currency exchange-rate tool.

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
- Task state is kept in memory for the demo; it is not a durable production datastore.
- The router is deterministic and uses word-boundary matching for single-word keywords to reduce accidental matches.
- The currency tool is deliberately non-live and should not be used for financial decisions.

## Limitations

- The currency rate is a fixed demonstration value, not a live market rate.
- Agent routing is keyword-based, so ambiguous requests may be routed to the fallback code agent.
- Task storage is process-local and is lost when the server restarts.
- The default agent setup requires a valid Groq API key.
- The current project is a demonstration architecture rather than a production-hardened distributed platform.

## Example Requests

- "What is the exchange rate between USD and EUR?"
- "Write a professional email asking for leave."
- "Create a Python function for binary search."
- "Explain convolutional neural networks."
- "Explain Q-learning."
- "Design a simple game concept."
