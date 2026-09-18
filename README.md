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


A2A defines the communication contract between the host/client and the multi-agent service. The specialist-to-specialist orchestration shown below is handled inside that service by the coordinator, not by separate network calls between every specialist.

### Request flow

1. The host sends a task to the A2A JSON-RPC endpoint.
2. The A2A task manager validates the request and creates the task.
3. The coordinator scores domain keywords and phrases using deterministic rules.
4. The collaboration planner converts the selection into a structured execution plan with specialist dependencies and parallel groups.
5. The selected specialist agents process the request with the configured Groq model.
6. Currency requests can call the MCP SSE tool server.
7. The task manager returns the result or streams task updates through SSE.

### Multi-agent collaboration

```text
User
  │
  ▼
Host / Client
  │
  ▼
A2A Server
  │
  ▼
Multi-Agent Router
  │
  ├── Simple request ──► One specialized agent
  │
  └── Cross-domain request
        │
        ├──► Lead Specialist A ──┐
        ├──► Lead Specialist B ──┼──► Dependent Specialist ──► Critic / Synthesizer ──► Final response
        └──► Lead Specialist C ──┘
                 │
                 └── Currency Agent ──► MCP Currency Tool
```

## Project Structure

```text
MCP_WITH_A2A/
├── app/
│   ├── agents/
│   │   ├── base.py
│   │   ├── critic.py
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
│   │   ├── task_store.py
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
│   ├── test_task_manager.py
│   ├── test_push_notification_auth.py
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
A2A_MAX_COLLABORATIVE_AGENTS=3
A2A_MAX_CONCURRENT_TASKS=8
A2A_RATE_LIMIT_PER_MINUTE=60
A2A_MAX_INPUT_CHARS=20000
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

The included tests cover routing, multi-agent handoffs, task lifecycle behavior, push-notification security, and MCP currency-tool input validation. Unit tests use fakes instead of live Groq calls.

```bash
pytest -q
ruff check app host frontend scripts tests
```

## Security and Reliability

- API credentials are loaded from environment variables and should never be committed.
- The A2A endpoint supports optional bearer authentication through `A2A_API_KEY`.
- The A2A endpoint applies a per-client rate limit and a maximum concurrent agent execution limit; these controls are process-local.
- Task input is validated for empty messages and has a configurable character limit.
- The A2A client uses request timeouts and validates JSON responses.
- Streaming uses asynchronous agent and SSE paths to avoid blocking the event loop.
- Push-notification callback URLs require HTTPS by default and private/loopback destinations are blocked.
- Push notification JWTs are RSA-signed, include a request-body digest and unique token ID, and receivers reject reused tokens within the validity window.
- A2A task state is persisted locally in SQLite by default, while live streaming subscribers and active workers remain process-local.
- Duplicate task IDs are idempotent; reusing an ID for a different session or message is rejected.
- Streaming tasks can be canceled while their worker is active.
- Currency rates come from a daily reference-rate provider; they are not suitable for live trading or guaranteed settlement prices.

## Limitations

- Currency rates are external daily reference rates and depend on provider availability.
- Agent routing is keyword-based, so ambiguous requests may still be misrouted or fall back to the code agent.
- SQLite persistence protects task records across a single server restart, but it does not provide distributed task state across multiple server processes.
- Live SSE subscriptions and running workers are still process-local; an active task cannot be resumed automatically after a server restart.
- Agent conversation memory is still in-process via LangGraph's memory checkpointer.
- The critic performs consistency and completeness review; it is not an external fact-checking or source-verification system.
- The default agent setup requires a valid Groq API key.
- The current project is a demonstration architecture rather than a production-hardened distributed platform.

### Collaboration behavior

The router keeps simple requests cheap by using one specialist. When a request clearly spans multiple domains—for example, “Build a Python CNN image-classification pipeline”—the coordinator selects up to three relevant specialists. The collaboration planner then records the execution mode, specialist steps, dependencies, handoffs, and rationale before any specialist runs. Lead specialists can run in parallel using separate conversation threads. Dependent work such as coding receives upstream specialist findings before execution, and a critic agent reviews the combined findings and produces the final response. The structured plan is also exposed in task metadata so clients can inspect how the collaboration was organized. If one specialist fails, the critic can still synthesize the successful findings and explicitly acknowledge the missing contribution.
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

### Multi-agent cost control

The collaboration coordinator limits a request to a small number of specialists (3 by default). For code-oriented cross-domain tasks, domain specialists run first and their findings are handed to the code specialist before critic synthesis. This keeps the workflow useful without turning every request into an uncontrolled LLM fan-out.
