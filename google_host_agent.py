import asyncio
import base64
import json
import uuid
from typing import Callable, List

from google.adk import Agent # type: ignore
from google.adk.agents.callback_context import CallbackContext # type: ignore
from google.adk.agents.invocation_context import InvocationContext # type: ignore
from google.adk.agents.readonly_context import ReadonlyContext # type: ignore
from google.adk.tools.tool_context import ToolContext # type: ignore
from google.genai import types # type: ignore
from google.adk.agents.run_config import RunConfig # type: ignore
from google.adk.sessions.in_memory_session_service import InMemorySessionService # type: ignore

from card_resolver import A2ACardResolver
from client import A2AClient
from custom_types import (
    AgentCard,
    DataPart,
    Message,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskSendParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg], Task]


class RemoteAgentConnections:
    """A class to hold the connections to the remote agents."""

    def __init__(self, agent_card: AgentCard):
        self.agent_client = A2AClient(agent_card)
        self.card = agent_card

        self.conversation_name = None
        self.conversation = None
        self.pending_tasks = set()

    def get_agent(self) -> AgentCard:
        return self.card

    async def send_task(
        self,
        request: TaskSendParams,
        task_callback: TaskUpdateCallback | None,
    ) -> Task | None:
        if self.card.capabilities.streaming:
            task = None
            if task_callback:
                task_callback(
                    Task(
                        id=request.id,
                        sessionId=request.sessionId,
                        status=TaskStatus(
                            state=TaskState.SUBMITTED,
                            message=request.message,
                        ),
                        history=[request.message],
                    )
                )
            async for response in self.agent_client.send_task_streaming(
                request.model_dump()
            ):
                merge_metadata(response.result, request)
                # For task status updates, we need to propagate metadata and provide
                # a unique message id.
                if (
                    hasattr(response.result, "status")
                    and hasattr(response.result.status, "message")
                    and response.result.status.message
                ):
                    merge_metadata(response.result.status.message, request.message)
                    m = response.result.status.message
                    if not m.metadata:
                        m.metadata = {}
                    if "message_id" in m.metadata:
                        m.metadata["last_message_id"] = m.metadata["message_id"]
                    m.metadata["message_id"] = str(uuid.uuid4())
                if task_callback:
                    task = task_callback(response.result)
                if hasattr(response.result, "final") and response.result.final:
                    break
            return task
        else:  # Non-streaming
            response = await self.agent_client.send_task(request.model_dump())
            merge_metadata(response.result, request)
            # For task status updates, we need to propagate metadata and provide
            # a unique message id.
            if (
                hasattr(response.result, "status")
                and hasattr(response.result.status, "message")
                and response.result.status.message
            ):
                merge_metadata(response.result.status.message, request.message)
                m = response.result.status.message
                if not m.metadata:
                    m.metadata = {}
                if "message_id" in m.metadata:
                    m.metadata["last_message_id"] = m.metadata["message_id"]
                m.metadata["message_id"] = str(uuid.uuid4())

            if task_callback:
                task_callback(response.result)
            return response.result


def merge_metadata(target, source):
    if not hasattr(target, "metadata") or not hasattr(source, "metadata"):
        return
    if target.metadata and source.metadata:
        target.metadata.update(source.metadata)
    elif source.metadata:
        target.metadata = dict(**source.metadata)


class HostAgent:
    """The host agent.

    This is the agent responsible for choosing which remote agents to send
    tasks to and coordinate their work.
    """

    def __init__(
        self,
        remote_agent_addresses: List[str],
        task_callback: TaskUpdateCallback | None = None,
    ):
        self.task_callback = task_callback
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        for address in remote_agent_addresses:
            card_resolver = A2ACardResolver(address)
            card = card_resolver.get_agent_card()
            remote_connection = RemoteAgentConnections(card)
            self.remote_agent_connections[card.name] = remote_connection
            self.cards[card.name] = card
        agent_info = []
        for ra in self.list_remote_agents():
            agent_info.append(json.dumps(ra))
        self.agents = "\n".join(agent_info)

    def register_agent_card(self, card: AgentCard):
        remote_connection = RemoteAgentConnections(card)
        self.remote_agent_connections[card.name] = remote_connection
        self.cards[card.name] = card
        agent_info = []
        for ra in self.list_remote_agents():
            agent_info.append(json.dumps(ra))
        self.agents = "\n".join(agent_info)

    def create_agent(self) -> Agent:
        agent = Agent(
            model="gemini-2.0-flash-001",
            name="host_agent",
            instruction=self.root_instruction,
            before_model_callback=self.before_model_callback,
            description=(
                "This agent orchestrates the decomposition of the user request into"
                " tasks that can be performed by the child agents."
            ),
            tools=[
                self.list_remote_agents,
                self.send_task,
            ],
        )
        agent
        return agent

    def root_instruction(self, context: ReadonlyContext) -> str:
        current_agent = self.check_state(context)
        return f"""You are a expert delegator that can delegate the user request to the
appropriate remote agents.

Discovery:
- You can use `list_remote_agents` to list the available remote agents you
can use to delegate the task.

Execution:
- For actionable tasks, you can use `create_task` to assign tasks to remote agents to perform.
Be sure to include the remote agent name when you response to the user.

You can use `check_pending_task_states` to check the states of the pending
tasks.

Please rely on tools to address the request, don't make up the response. If you are not sure, please ask the user for more details.
Focus on the most recent parts of the conversation primarily.

If there is an active agent, send the request to that agent with the update task tool.

Agents:
{self.agents}

Current agent: {current_agent["active_agent"]}
"""

    def check_state(self, context: ReadonlyContext):
        state = context.state
        if (
            "session_id" in state
            and "session_active" in state
            and state["session_active"]
            and "agent" in state
        ):
            return {"active_agent": f"{state['agent']}"}
        return {"active_agent": "None"}

    def before_model_callback(self, callback_context: CallbackContext, llm_request):
        state = callback_context.state
        if "session_active" not in state or not state["session_active"]:
            if "session_id" not in state:
                state["session_id"] = str(uuid.uuid4())
            state["session_active"] = True

    def list_remote_agents(self):
        """List the available remote agents you can use to delegate the task."""
        if not self.remote_agent_connections:
            return []

        remote_agent_info = []
        for card in self.cards.values():
            remote_agent_info.append(
                {"name": card.name, "description": card.description}
            )
        return remote_agent_info

    async def send_task(self, agent_name: str, message: str, tool_context: ToolContext):
        """Sends a task either streaming (if supported) or non-streaming.

        This will send a message to the remote agent named agent_name.

        Args:
          agent_name: The name of the agent to send the task to.
          message: The message to send to the agent for the task.
          tool_context: The tool context this method runs in.

        Yields:
          A dictionary of JSON data.
        """
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")
        state = tool_context.state
        state["agent"] = agent_name
        card = self.cards[agent_name]
        client = self.remote_agent_connections[agent_name]
        if not client:
            raise ValueError(f"Client not available for {agent_name}")
        if "task_id" in state:
            taskId = state["task_id"]
        else:
            taskId = str(uuid.uuid4())
        sessionId = state["session_id"]
        task: Task
        messageId = ""
        metadata = {}
        if "input_message_metadata" in state:
            metadata.update(**state["input_message_metadata"])
            if "message_id" in state["input_message_metadata"]:
                messageId = state["input_message_metadata"]["message_id"]
        if not messageId:
            messageId = str(uuid.uuid4())
        metadata.update(**{"conversation_id": sessionId, "message_id": messageId})
        request: TaskSendParams = TaskSendParams(
            id=taskId,
            sessionId=sessionId,
            message=Message(
                role="user",
                parts=[TextPart(text=message)],
                metadata=metadata,
            ),
            acceptedOutputModes=["text", "text/plain", "image/png"],
            # pushNotification=None,
            metadata={"conversation_id": sessionId},
        )
        task = await client.send_task(request, self.task_callback)
        # Assume completion unless a state returns that isn't complete
        state["session_active"] = task.status.state not in [
            TaskState.COMPLETED,
            TaskState.CANCELED,
            TaskState.FAILED,
            TaskState.UNKNOWN,
        ]
        if task.status.state == TaskState.INPUT_REQUIRED:
            # Force user input back
            tool_context.actions.skip_summarization = True
            tool_context.actions.escalate = True
        elif task.status.state == TaskState.CANCELED:
            # Open question, should we return some info for cancellation instead
            raise ValueError(f"Agent {agent_name} task {task.id} is cancelled")
        elif task.status.state == TaskState.FAILED:
            # Raise error for failure
            raise ValueError(f"Agent {agent_name} task {task.id} failed")
        response = []
        if task.status.message:
            # Assume the information is in the task message.
            response.extend(convert_parts(task.status.message.parts, tool_context))
        if task.artifacts:
            for artifact in task.artifacts:
                response.extend(convert_parts(artifact.parts, tool_context))
        return response


def convert_parts(parts: list[Part], tool_context: ToolContext):
    rval = []
    for p in parts:
        rval.append(convert_part(p, tool_context))
    return rval


def convert_part(part: Part, tool_context: ToolContext):
    if part.type == "text":
        return part.text
    elif part.type == "data":
        return part.data
    elif part.type == "file":
        # Repackage A2A FilePart to google.genai Blob
        # Currently not considering plain text as files
        file_id = part.file.name
        file_bytes = base64.b64decode(part.file.bytes)
        file_part = types.Part(
            inline_data=types.Blob(mime_type=part.file.mimeType, data=file_bytes)
        )
        tool_context.save_artifact(file_id, file_part)
        tool_context.actions.skip_summarization = True
        tool_context.actions.escalate = True
        return DataPart(data={"artifact-file-id": file_id})
    return f"Unknown type: {p.type}"



# ---------------------------------------------------------
# Your HostAgent code (from your snippet)
# ---------------------------------------------------------
host_agent = HostAgent(["http://localhost:8000"])
root_agent = host_agent.create_agent()

# ---------------------------------------------------------
# 1. Create an in-memory session service
# ---------------------------------------------------------
session_service = InMemorySessionService()

# ---------------------------------------------------------
# 2. Create a session with the required fields
# ---------------------------------------------------------
my_session = session_service.create_session(
    app_name="test_app", user_id="test_user", session_id="session-123"
)

# ---------------------------------------------------------
# 3. Provide a basic RunConfig with response_modalities
# ---------------------------------------------------------
run_config = RunConfig(response_modalities=["text"])

# ---------------------------------------------------------
# 4. Build the InvocationContext
# ---------------------------------------------------------
context = InvocationContext(
    session_service=session_service,
    memory_service=None,
    artifact_service=None,
    session=my_session,  # We just created
    agent=root_agent,
    invocation_id=str(uuid.uuid4()),
    run_config=run_config,
)


# ---------------------------------------------------------
# 5. Run your agent with run_async(...)
# ---------------------------------------------------------
async def main():
    async for event in root_agent.run_async(context):
        if event.content:
            print("Agent output:", event.content.text())


asyncio.run(main())