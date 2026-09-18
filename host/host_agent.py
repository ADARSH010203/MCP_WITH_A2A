import uuid
from typing import Any

import requests
import typer
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from app.a2a.models import AgentCard, TaskState
from app.config.settings import settings

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent


class RemoteAgentClient:
    """Communicates with a single remote agent (A2A) in synchronous mode."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.agent_card: AgentCard | None = None

    def fetch_agent_card(self) -> AgentCard:
        """Fetch and validate the remote agent's A2A Agent Card."""
        url = f"{self.base_url}/.well-known/agent.json"
        headers = (
            {"Authorization": f"Bearer {settings.a2a_api_key}"}
            if settings.a2a_api_key
            else {}
        )
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        card = AgentCard.model_validate(response.json())
        self.agent_card = card
        return card

    def send_task(self, task_id: str, session_id: str, message_text: str) -> dict[str, Any]:
        """POST / with JSON-RPC request: method=tasks/send."""
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tasks/send",
            "params": {
                "id": task_id,
                "sessionId": session_id,
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message_text}],
                },
            },
        }
        headers = {"Authorization": f"Bearer {settings.a2a_api_key}"} if settings.a2a_api_key else {}
        r = requests.post(self.base_url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        resp = r.json()
        if "error" in resp and resp["error"] is not None:
            raise RuntimeError(f"Remote agent error: {resp['error']}")
        return resp.get("result", {})


class HostAgent:
    """Holds references to multiple RemoteAgentClients for one host session."""

    def __init__(self, remote_addresses: list[str]):
        self.clients = {}
        self.session_id = f"host-{uuid.uuid4().hex}"
        self.initialization_errors: dict[str, str] = {}
        for addr in remote_addresses:
            self.clients[addr] = RemoteAgentClient(addr)

    def initialize(self):
        """Fetch agent cards without preventing other agents from connecting."""
        self.initialization_errors.clear()
        for addr, client in self.clients.items():
            try:
                client.fetch_agent_card()
            except Exception as exc:
                self.initialization_errors[addr] = str(exc)

    def list_agents_info(self) -> list:
        """Return information for successfully discovered remote agents."""
        infos = []
        for client in self.clients.values():
            card = client.agent_card
            if card is None:
                continue

            infos.append(
                {
                    "name": card.name,
                    "description": card.description,
                    "url": card.url,
                    "streaming": card.capabilities.streaming,
                }
            )
        return infos

    def get_client_by_name(self, agent_name: str) -> RemoteAgentClient | None:
        """Find a client whose AgentCard name matches `agent_name`."""
        for c in self.clients.values():
            if c.agent_card and c.agent_card.name == agent_name:
                return c
        return None

    def send_task(self, agent_name: str, message: str) -> str:
        """
        Actually send the user's request to the remote agent via tasks/send JSON-RPC.
        Returns a textual summary or error message.
        """
        client = self.get_client_by_name(agent_name)
        if not client or not client.agent_card:
            return f"Error: No agent card found for '{agent_name}'."

        task_id = str(uuid.uuid4())
        session_id = self.session_id

        try:
            result = client.send_task(task_id, session_id, message)
            # Check final state
            state = result.get("status", {}).get("state", "unknown")
            if state == TaskState.COMPLETED:
                artifacts = result.get("artifacts") or []
                content_parts: list[str] = []
                metadata: dict[str, Any] = {}

                for artifact in artifacts:
                    if not isinstance(artifact, dict):
                        continue
                    artifact_metadata = artifact.get("metadata")
                    if isinstance(artifact_metadata, dict):
                        metadata.update(artifact_metadata)

                    for part in artifact.get("parts") or []:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = str(part.get("text", "")).strip()
                            if text:
                                content_parts.append(text)

                if content_parts:
                    return "\n\n".join(content_parts)

                return "The remote agent completed the task but returned no text content."
            elif state == TaskState.INPUT_REQUIRED:
                message = result.get("status", {}).get("message", {})
                parts = message.get("parts") if isinstance(message, dict) else []
                text_parts = [
                    str(part.get("text", "")).strip()
                    for part in (parts or [])
                    if isinstance(part, dict)
                    and part.get("type") == "text"
                    and str(part.get("text", "")).strip()
                ]
                return "\n\n".join(text_parts) or f"Task {task_id} needs more input."
            else:
                return f"Task {task_id} ended with state={state}."
        except Exception as exc:
            return f"Remote agent call failed: {exc}"


def make_list_agents_tool(host_agent: HostAgent):
    """Return a synchronous tool function that calls host_agent.list_agents_info()."""

    @tool
    def list_remote_agents_tool() -> list:
        """List available remote agents (name, url, streaming)."""
        return host_agent.list_agents_info()

    return list_remote_agents_tool


def make_send_task_tool(host_agent: HostAgent):
    """Return a synchronous tool function that calls host_agent.send_task(...)."""

    @tool
    def send_task_tool(agent_name: str, message: str) -> str:
        """
        Synchronous tool: sends 'message' to 'agent_name'
        via JSON-RPC and returns the result.
        """
        return host_agent.send_task(agent_name, message)

    return send_task_tool


def build_react_agent(host_agent: HostAgent):
    # Create the top-level LLM using Groq
    llm = ChatGroq(
        temperature=0,
        model=settings.groq_model,
        streaming=False
    )
    memory = MemorySaver()

    # Make the two tools referencing our host_agent
    list_tool = make_list_agents_tool(host_agent)
    send_tool = make_send_task_tool(host_agent)

    system_prompt = """
You are a Host Agent that delegates requests to known remote agents.
You have two tools:
1) list_remote_agents_tool(): Lists the remote agents (their name, URL, streaming).
2) send_task_tool(agent_name, message): Sends a text request to the agent.

Use the available agent list to choose the appropriate remote agent. Do not invent an agent that is not present in the list.
Return the final result to the user.
"""

    agent = create_react_agent(
        model=llm,
        tools=[list_tool, send_tool],
        checkpointer=memory,
        prompt=system_prompt,
    )
    return agent


app = typer.Typer()


@app.command()
def run_agent(remote_url: str = "http://localhost:8000"):
    """
    Start a synchronous HostAgent pointing at 'remote_url'
    and run a simple conversation loop.
    """
    # 1) Build the HostAgent
    host_agent = HostAgent([remote_url])

    host_agent.initialize()
    react_agent = build_react_agent(host_agent)

    typer.echo(f"Host agent ready. Connected to: {remote_url}")
    typer.echo("Type 'quit' or 'exit' to stop.")

    while True:
        user_msg = typer.prompt("\nUser")
        if user_msg.strip().lower() in ["quit", "exit", "bye"]:
            typer.echo("Goodbye!")
            break

        raw_result = react_agent.invoke(
            {"messages": [{"role": "user", "content": user_msg}]},
            config={"configurable": {"thread_id": "cli-session"}},
        )

        final_text = None

        # If 'raw_result' is a dictionary with "messages", try to find the last AIMessage
        if isinstance(raw_result, dict) and "messages" in raw_result:
            all_msgs = raw_result["messages"]
            for msg in reversed(all_msgs):
                if isinstance(msg, AIMessage):
                    final_text = msg.content
                    break
        else:
            # Otherwise, it's likely a plain string
            if isinstance(raw_result, str):
                final_text = raw_result
            else:
                # fallback: convert whatever it is to string
                final_text = str(raw_result)

        # Now print only the final AIMessage content
        typer.echo(f"HostAgent: {final_text}")


def main():
    """
    Start the host-agent CLI.
    """
    app()


if __name__ == "__main__":
    main()