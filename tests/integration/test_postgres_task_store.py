import os

import pytest

from app.a2a.models import Message, Task, TaskState, TaskStatus, TextPart
from app.a2a.postgres_task_store import PostgresTaskStore


POSTGRES_URL = os.getenv("TEST_POSTGRES_URL", "").strip()

pytestmark = pytest.mark.integration


def _task(task_id: str = "postgres-task") -> Task:
    return Task(
        id=task_id,
        sessionId="postgres-session",
        status=TaskStatus(state=TaskState.SUBMITTED),
        history=[
            Message(
                role="user",
                parts=[TextPart(text="postgres integration")],
            )
        ],
    )


@pytest.fixture
def postgres_store():
    if not POSTGRES_URL:
        pytest.skip("TEST_POSTGRES_URL is not configured")
    store = PostgresTaskStore(POSTGRES_URL)
    yield store
    store.close()


def test_postgres_store_persists_task_and_lease(postgres_store):
    task, created = postgres_store.create_task_if_absent(_task())

    assert created is True
    assert postgres_store.load_task(task.id) is not None
    assert postgres_store.claim_task(task.id, "worker-a", 60) is True
    assert postgres_store.claim_task(task.id, "worker-b", 60) is False
    assert postgres_store.renew_task_lease(task.id, "worker-a", 60) is True
    assert postgres_store.release_task(task.id, "worker-a") is True
    assert postgres_store.claim_task(task.id, "worker-b", 60) is True

    postgres_store.save_task(
        task.model_copy(update={"status": TaskStatus(state=TaskState.COMPLETED)})
    )
    restored = postgres_store.load_task(task.id)
    assert restored is not None
    assert restored.status.state == TaskState.COMPLETED


def test_postgres_store_creation_is_idempotent_under_repeat(postgres_store):
    first, first_created = postgres_store.create_task_if_absent(
        _task("repeat-task")
    )
    second, second_created = postgres_store.create_task_if_absent(
        _task("repeat-task")
    )

    assert first_created is True
    assert second_created is False
    assert first.id == second.id