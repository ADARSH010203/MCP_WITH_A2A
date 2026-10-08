import asyncio

from app.a2a.models import Message, Task, TaskSendParams, TaskState, TaskStatus, TextPart
from app.a2a.task_store import SQLiteTaskStore


def _task(task_id: str = "shared-task") -> Task:
    return Task(
        id=task_id,
        sessionId="shared-session",
        status=TaskStatus(state=TaskState.SUBMITTED),
        history=[Message(role="user", parts=[TextPart(text="hello")])],
    )


def _params(task_id: str = "shared-task") -> TaskSendParams:
    return TaskSendParams(
        id=task_id,
        sessionId="shared-session",
        message=Message(
            role="user",
            parts=[TextPart(text="hello")],
        ),
    )


def test_task_store_creation_is_atomic_across_workers(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first = SQLiteTaskStore(db_path)
    second = SQLiteTaskStore(db_path)

    created_one = first.create_task_if_absent(_task())
    created_two = second.create_task_if_absent(_task())

    assert created_one[1] is True
    assert created_two[1] is False
    assert created_two[0].id == "shared-task"

    first.close()
    second.close()


def test_task_lease_is_exclusive_until_release(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first = SQLiteTaskStore(db_path)
    second = SQLiteTaskStore(db_path)
    first.create_task_if_absent(_task())

    assert first.claim_task("shared-task", "worker-a", 60) is True
    assert second.claim_task("shared-task", "worker-b", 60) is False
    assert second.task_claimed_by_other("shared-task", "worker-b") is True

    assert first.release_task("shared-task", "worker-a") is True
    assert second.claim_task("shared-task", "worker-b", 60) is True

    first.close()
    second.close()


def test_expired_task_lease_can_be_taken_over(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first = SQLiteTaskStore(db_path)
    second = SQLiteTaskStore(db_path)
    first.create_task_if_absent(_task())

    assert first.claim_task("shared-task", "worker-a", 0.05) is True
    asyncio.run(asyncio.sleep(0.08))

    assert second.claim_task("shared-task", "worker-b", 60) is True
    assert second.purge_expired_leases() == 0

    first.close()
    second.close()


def test_task_state_is_read_from_durable_store_between_managers(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    first = SQLiteTaskStore(db_path)
    second = SQLiteTaskStore(db_path)
    created, _ = first.create_task_if_absent(_task())

    updated = created.model_copy(
        update={
            "status": TaskStatus(state=TaskState.COMPLETED),
        }
    )
    first.save_task(updated)

    restored = second.load_task("shared-task")
    assert restored is not None
    assert restored.status.state == TaskState.COMPLETED

    first.close()
    second.close()
