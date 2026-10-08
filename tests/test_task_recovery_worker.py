import asyncio

from app.a2a.models import Message, TaskSendParams, TaskState, TextPart
from app.a2a.task_manager import AgentTaskManager
from app.a2a.task_store import SQLiteTaskStore


class FakeNotificationAuth:
    async def verify_push_notification_url(self, url: str) -> bool:
        return True

    async def send_push_notification(self, url: str, data: dict) -> None:
        return None


class FakeAgent:
    def __init__(self):
        self.invoke_calls = 0

    def invoke(self, query: str, session_id: str) -> dict:
        self.invoke_calls += 1
        return {
            "status": "completed",
            "is_task_complete": True,
            "require_user_input": False,
            "content": f"recovered: {query}",
        }


def _params(task_id: str) -> TaskSendParams:
    return TaskSendParams(
        id=task_id,
        sessionId="recovery-session",
        message=Message(
            role="user",
            parts=[TextPart(text="recover me")],
        ),
    )


def test_recovery_worker_reprocesses_expired_work(tmp_path):
    async def scenario():
        store = SQLiteTaskStore(str(tmp_path / "tasks.db"))
        agent = FakeAgent()
        manager = AgentTaskManager(
            agent,
            FakeNotificationAuth(),
            store=store,
        )

        await manager.get_or_create_task(_params("recovery-task"))
        assert store.claim_task("recovery-task", "dead-worker", 0.05) is True
        await asyncio.sleep(0.08)

        recovered = await manager.recover_tasks_once()

        assert recovered == 1
        assert agent.invoke_calls == 1
        task = await manager.get_stored_task("recovery-task")
        assert task is not None
        assert task.status.state == TaskState.COMPLETED

        store.close()

    asyncio.run(scenario())


def test_recovery_worker_does_not_take_live_task(tmp_path):
    async def scenario():
        store = SQLiteTaskStore(str(tmp_path / "tasks.db"))
        agent = FakeAgent()
        manager = AgentTaskManager(
            agent,
            FakeNotificationAuth(),
            store=store,
        )

        await manager.get_or_create_task(_params("live-task"))
        assert store.claim_task("live-task", "live-worker", 60) is True

        recovered = await manager.recover_tasks_once()

        assert recovered == 0
        assert agent.invoke_calls == 0

        store.close()

    asyncio.run(scenario())


def test_recovery_worker_lifecycle_is_idempotent(tmp_path):
    async def scenario():
        store = SQLiteTaskStore(str(tmp_path / "tasks.db"))
        manager = AgentTaskManager(
            FakeAgent(),
            FakeNotificationAuth(),
            store=store,
        )
        manager.recovery_worker_enabled = True

        await manager.start_recovery_worker()
        first = manager.recovery_worker_task
        await manager.start_recovery_worker()
        assert manager.recovery_worker_task is first
        assert first is not None

        await manager.stop_recovery_worker()
        assert manager.recovery_worker_task is None

        store.close()

    asyncio.run(scenario())
