import asyncio

from app.a2a.models import (
    CancelTaskRequest,
    JSONRPCResponse,
    Message,
    SendTaskRequest,
    SendTaskStreamingRequest,
    TaskState,
    TaskSendParams,
    TextPart,
)
from app.a2a.task_manager import AgentTaskManager
from app.a2a.task_store import SQLiteTaskStore


class FakeNotificationAuth:
    async def verify_push_notification_url(self, url: str) -> bool:
        return True

    async def send_push_notification(self, url: str, data: dict) -> None:
        return None


class FakeAgent:
    def __init__(self, response: dict):
        self.response = response
        self.invoke_calls = 0

    def invoke(self, query: str, session_id: str) -> dict:
        self.invoke_calls += 1
        return self.response


class FakeStreamingAgent:
    def __init__(self):
        self.stream_calls = 0

    async def stream(self, query: str, session_id: str):
        self.stream_calls += 1
        yield {
            "status": "completed",
            "is_task_complete": True,
            "require_user_input": False,
            "content": "done",
        }


class BlockingStreamingAgent:
    def __init__(self):
        self.stream_calls = 0
        self.started = asyncio.Event()

    async def stream(self, query: str, session_id: str):
        self.stream_calls += 1
        self.started.set()
        await asyncio.Event().wait()
        yield {}


def make_request(
    task_id: str = "task-1",
    session_id: str = "session-1",
    text: str = "Hello",
) -> SendTaskRequest:
    return SendTaskRequest(
        id="rpc-1",
        params=TaskSendParams(
            id=task_id,
            sessionId=session_id,
            message=Message(role="user", parts=[TextPart(text=text)]),
        ),
    )


def make_stream_request(task_id: str = "stream-1") -> SendTaskStreamingRequest:
    return SendTaskStreamingRequest(
        id="rpc-stream",
        params=TaskSendParams(
            id=task_id,
            sessionId="session-1",
            message=Message(role="user", parts=[TextPart(text="run")]),
        ),
    )


def test_duplicate_task_id_does_not_run_agent_twice():
    async def scenario():
        agent = FakeAgent(
            {
                "status": "completed",
                "is_task_complete": True,
                "require_user_input": False,
                "content": "done",
            }
        )
        manager = AgentTaskManager(
            agent,
            FakeNotificationAuth(),
            store=SQLiteTaskStore(":memory:"),
        )
        request = make_request()

        first = await manager.on_send_task(request)
        second = await manager.on_send_task(request)

        assert agent.invoke_calls == 1
        assert first.result is not None
        assert second.result is not None
        assert second.result.id == first.result.id
        assert second.result.status.state == TaskState.COMPLETED

    asyncio.run(scenario())


def test_reusing_task_id_with_different_request_is_rejected():
    async def scenario():
        agent = FakeAgent(
            {
                "status": "completed",
                "is_task_complete": True,
                "require_user_input": False,
                "content": "done",
            }
        )
        manager = AgentTaskManager(
            agent,
            FakeNotificationAuth(),
            store=SQLiteTaskStore(":memory:"),
        )

        await manager.on_send_task(make_request())
        conflicting = make_request(text="Different request")
        response = await manager.on_send_task(conflicting)

        assert response.error is not None
        assert response.error.code == -32602
        assert agent.invoke_calls == 1

    asyncio.run(scenario())


def test_streaming_retry_does_not_start_second_worker():
    async def scenario():
        agent = FakeStreamingAgent()
        manager = AgentTaskManager(
            agent,
            FakeNotificationAuth(),
            store=SQLiteTaskStore(":memory:"),
        )

        response = await manager.on_send_task_subscribe(make_stream_request())
        assert not isinstance(response, JSONRPCResponse)

        events = []
        async for event in response:
            events.append(event)

        retry = await manager.on_send_task_subscribe(make_stream_request())
        retry_events = []
        async for event in retry:
            retry_events.append(event)

        assert agent.stream_calls == 1
        assert events[-1].result is not None
        assert events[-1].result.status.state == TaskState.COMPLETED
        assert retry_events[-1].result is not None
        assert retry_events[-1].result.status.state == TaskState.COMPLETED

    asyncio.run(scenario())


def test_streaming_task_can_be_canceled():
    async def scenario():
        agent = BlockingStreamingAgent()
        manager = AgentTaskManager(
            agent,
            FakeNotificationAuth(),
            store=SQLiteTaskStore(":memory:"),
        )
        request = make_stream_request("cancel-me")

        response = await manager.on_send_task_subscribe(request)
        assert not isinstance(response, JSONRPCResponse)

        await agent.started.wait()

        cancel_request = CancelTaskRequest(
            id="cancel-rpc",
            params={"id": "cancel-me"},
        )
        cancel_response = await manager.on_cancel_task(cancel_request)

        assert cancel_response.result is not None
        assert cancel_response.result.status.state == TaskState.CANCELED

        events = []
        async for event in response:
            events.append(event)

        assert events[-1].result is not None
        assert events[-1].result.status.state == TaskState.CANCELED

    asyncio.run(scenario())



def test_task_state_survives_manager_restart(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "tasks.db")
        agent = FakeAgent(
            {
                "status": "completed",
                "is_task_complete": True,
                "require_user_input": False,
                "content": "persisted",
            }
        )

        manager_one = AgentTaskManager(
            agent,
            FakeNotificationAuth(),
            store=SQLiteTaskStore(db_path),
        )
        request = make_request("persistent-task")
        first = await manager_one.on_send_task(request)
        assert first.result is not None
        assert first.result.status.state == TaskState.COMPLETED

        manager_two = AgentTaskManager(
            FakeAgent(
                {
                    "status": "completed",
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": "should not run",
                }
            ),
            FakeNotificationAuth(),
            store=SQLiteTaskStore(db_path),
        )
        restored = await manager_two.get_stored_task("persistent-task")
        assert restored is not None
        assert restored.status.state == TaskState.COMPLETED
        assert restored.artifacts

    asyncio.run(scenario())
