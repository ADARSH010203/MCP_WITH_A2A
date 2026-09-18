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
3. The coordinator matches the request against a validated agent capability registry using deterministic triggers and priorities.
4. The collaboration planner converts the selection into a dependency graph and structured execution plan with parallel groups.
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
│   │   ├── router.py
│   │   ├── registry.py
│   │   ├── remote_specialist.py
│   │   ├── planner.py
│   │   └── tracing.py
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
│   ├── run_mcp_server.py
│   └── run_specialist_a2a_server.py
├── tests/
│   ├── test_router.py
│   ├── test_planner.py
│   ├── test_task_manager.py
│   ├── test_tracing.py
│   ├── test_remote_specialist.py
│   ├── test_remote_config.py
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
A2A_SPECIALIST_TIMEOUT_SECONDS=45
A2A_SPECIALIST_MAX_RETRIES=1
A2A_MAX_AGENT_CALLS_PER_TASK=6
A2A_SPECIALIST_URLS=
A2A_REMOTE_CONNECT_TIMEOUT_SECONDS=10
A2A_REMOTE_REQUEST_TIMEOUT_SECONDS=55
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

## Run an Independent Specialist

Phase 5 supports deploying any built-in specialist as its own A2A service.

For example, start a standalone code specialist:

```bash
python -m scripts.run_specialist_a2a_server --agent code --port 8101
```

Each standalone specialist gets its own SQLite task database by default, so multiple specialists do not share task records.

Start a second specialist in another process:

```bash
python -m scripts.run_specialist_a2a_server --agent deep_learning --port 8102
```

Then point the coordinator at those services:

```env
A2A_SPECIALIST_URLS=code=http://127.0.0.1:8101;deep_learning=http://127.0.0.1:8102
```

Only configured specialists become remote calls. All other specialists continue using their local implementations, so the deployment can be migrated incrementally.

The coordinator discovers each remote Agent Card from `/.well-known/agent.json` before sending work. Specialist requests use the A2A `tasks/send` contract, and streaming uses `tasks/sendSubscribe`. The coordinator still owns the dependency plan and critic synthesis; the specialist service owns only its domain task.

### Remote specialist architecture

```text
                         A2A
                 ┌─────────────────┐
                 │   Coordinator   │
                 └────────┬────────┘
                          │
          ┌───────────────┼────────────────┐
          │               │                │
          ▼               ▼                ▼
   Code Specialist   DL Specialist   Local Specialist
      :8101             :8102
          │               │
       Agent Card      Agent Card
          │               │
       Groq/Tools     Groq/Tools
```

This is the first phase where specialist services can cross a process or machine boundary. The coordinator remains the orchestration authority, but a dependent specialist can now be an independent remote A2A service; its upstream findings are sent as task input over A2A instead of invoking that specialist's Python class directly. This is coordinator-mediated distributed collaboration, not direct peer-to-peer calls between every specialist.

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

The included tests cover routing, capability registration, multi-agent handoffs, task lifecycle behavior, tracing, remote specialist configuration, push-notification security, and MCP currency-tool input validation. Unit tests use fakes instead of live Groq calls.

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
- Specialist calls use a configurable timeout, and transient invocation errors can be retried once by default.
- Each top-level task has a shared agent-call budget that includes specialist retries and the final critic call.
- A timed-out call is isolated from the coordinator; Python cannot forcibly stop a running thread, so the underlying provider call may finish later in the background.

## Limitations

- Currency rates are external daily reference rates and depend on provider availability.
- Agent routing is deterministic and registry-driven, but ambiguous requests can still be misrouted or fall back to the code agent.
- SQLite persistence protects task records across a single server restart, but it does not provide distributed task state across multiple server processes.
- Live SSE subscriptions and running workers are still process-local; an active task cannot be resumed automatically after a server restart.
- Agent conversation memory is still in-process via LangGraph's memory checkpointer.
- The critic performs consistency and completeness review; it is not an external fact-checking or source-verification system.
- The default agent setup requires a valid Groq API key.
- The current project is a demonstration architecture rather than a production-hardened distributed platform.
- Remote specialist endpoints are operator-configured; the coordinator discovers each configured service only through explicit Agent Card retrieval.
- Remote specialists share the configured A2A bearer credential when authentication is enabled; separate per-service credentials are not modeled yet.

### Collaboration behavior

The router keeps simple requests cheap by using one specialist. When a request clearly spans multiple domains—for example, “Build a Python CNN image-classification pipeline”—the coordinator selects up to three relevant specialists. The collaboration planner then records the execution mode, specialist steps, dependencies, handoffs, and rationale before any specialist runs. Lead specialists can run in parallel using separate conversation threads. Dependent work such as coding receives upstream specialist findings before execution, and a critic agent reviews the combined findings and produces the final response. The structured plan is also exposed in task metadata so clients can inspect how the collaboration was organized. If one specialist fails, the critic can still synthesize the successful findings and explicitly acknowledge the missing contribution.


### Capability registry and dependency graph

Routing metadata is centralized in `app/routing/registry.py`. Each specialist declares its capabilities, trigger phrases, routing priority, supported input/output types, parallel-execution policy, and upstream dependencies.

The planner consumes those dependencies as a graph rather than relying on a single hardcoded handoff loop. For a request that needs domain guidance before implementation, the graph can produce:

```text
Deep Learning ──────┐
                    ├──> Code ───> Critic
Game ───────────────┤
RL ─────────────────┘
```

The dependency graph is validated for unknown dependencies and cycles before a plan is executed. Independent specialists share a parallel execution group; dependent specialists run only after the required upstream group has produced its findings. A trace event records whether each specialist execution used the local implementation or a remote A2A service.

This remains deterministic and explainable. There is no LLM-based routing decision in this phase.

### Collaboration observability

Each top-level request gets a lightweight in-process trace with a unique trace ID. The trace records the planner decision, specialist start/completion status, retries, handoffs, critic execution, and final coordinator status with elapsed time. The latest trace is attached to router responses and A2A task/stream metadata, so clients can inspect the execution path without parsing log text.

Example trace stages:

```text
plan_created
specialist_started
specialist_completed
specialist_retry
handoff
critic_started
critic_completed
request_completed
```

Trace data is intended for debugging and UI visibility, not as a distributed tracing backend. It remains process-local and is carried with the task metadata.

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

Each top-level request also has a shared model-call budget (6 by default). Specialist failures may be retried once, while timeouts are not retried because the original thread may still be running. If the critic cannot run because the budget is exhausted or the critic times out, successful specialist findings are returned without synthesis and critic_reviewed remains false.
