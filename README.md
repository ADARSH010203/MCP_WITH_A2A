# MCP + A2A Multi-Agent System

A modular Python multi-agent system that combines **Agent-to-Agent (A2A)** communication with the **Model Context Protocol (MCP)**.

The project receives a user request through a host/client, routes it to a specialized agent, and uses MCP tools where external tool access is required.

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

## Project Structure

```text
MCP_WITH_A2A/
├── app/
│   ├── agents/
│   │   ├── currency.py
│   │   └── specialized.py
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
│   ├── routing/
│   │   └── router.py
│   └── config/
│       └── constants.py
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

Create a local `.env` file from `.env.example`:

```env
GROQ_API_KEY=your_groq_api_key
```

Never commit a real API key.

## Run the MCP Server

Start the MCP server first:

```bash
python -m scripts.run_mcp_server
```

The demo MCP SSE endpoint is:

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

## Example Requests

- "What is the exchange rate between USD and EUR?"
- "Write a professional email asking for leave."
- "Create a Python function for binary search."
- "Explain convolutional neural networks."
- "Explain Q-learning."
- "Design a simple game concept."

## Notes

The currency MCP tool currently uses a deterministic placeholder rate for demonstration. It is not a live financial-data service.

The refactor is intentionally structural: the existing A2A, MCP, host, and agent workflows are separated into clear packages so the project can be extended without keeping all components in the repository root.
