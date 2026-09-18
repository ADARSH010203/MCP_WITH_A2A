# A2A + MCP Multi-Agent System

A Python multi-agent example that combines **Agent-to-Agent (A2A)** communication with the **Model Context Protocol (MCP)**.

The project uses one A2A server to expose a multi-purpose agent. The server routes incoming tasks to specialized agents such as currency, email, coding, image, game, deep learning, reinforcement learning, and DSA. The currency agent demonstrates MCP tool access through an MCP server.

## Architecture

```text
User / Client
     |
     v
 A2A Host / Client
     |
     v
 Multi-Purpose A2A Agent
     |
     +--> Currency Agent ----> MCP Server ----> Exchange-rate tool
     +--> Email Agent
     +--> Code Agent
     +--> Image Agent
     +--> Game Agent
     +--> Deep Learning Agent
     +--> Reinforcement Learning Agent
     +--> DSA Agent
```

### Main files

| File | Purpose |
|---|---|
| `agentpartner.py` | Starts the A2A server and publishes the agent card. |
| `multi_agent.py` | Routes a request to the appropriate specialized agent. |
| `agent.py` | Currency agent with MCP tool integration. |
| `specialized_agents.py` | Shared base class and specialized LLM agents. |
| `mcp_app.py` | MCP server exposing the currency tool. |
| `server.py` | A2A JSON-RPC server and streaming endpoint handling. |
| `client.py` | Async A2A client for normal and SSE requests. |
| `custom_types.py` | A2A request, response, task, and agent-card models. |

## Setup

Use Python 3.11+.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Create a local `.env` file:

```env
GROQ_API_KEY=your_groq_api_key
```

Do not commit the real API key.

## Run

Start the MCP server first:

```bash
python mcp_app.py
```

Start the A2A server in a second terminal:

```python
python agentpartner.py --host 127.0.0.1 --port 8000
```

The A2A agent card is available at:

```text
http://127.0.0.1:8000/.well-known/agent.json
```

The MCP SSE endpoint is available at:

```text
http://127.0.0.1:3000/sse
```

## Example requests

Currency request:

```text
What is the exchange rate between USD and EUR?
```

Coding request:

```text
Write a Python function to validate an email address.
```

DSA request:

```text
Explain binary search and its time complexity.
```

## Notes

The current currency tool intentionally returns a placeholder rate. It is useful for demonstrating MCP tool calling, but it is **not a live market-rate service**.

The repository also contains some experimental/demo modules and local assets. The production path is the A2A server, specialized-agent routing, and MCP integration described above.
