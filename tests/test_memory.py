"""Persistent memory and SQLite infrastructure tests."""

from app.a2a.models import Task, TaskState, TaskStatus
from app.a2a.task_store import SQLiteTaskStore
from app.memory.sqlite_memory import SQLiteConversationMemory


def test_memory_survives_store_reopen(tmp_path):
    path = tmp_path / "memory.db"

    first = SQLiteConversationMemory(str(path), max_turns=4, max_chars=100)
    first.append("session-1", "code", "user", "Build a Python API")
    first.append("session-1", "code", "assistant", "Use FastAPI.")
    first.close()

    second = SQLiteConversationMemory(str(path), max_turns=4, max_chars=100)
    assert second.recent("session-1", "code") == [
        ("user", "Build a Python API"),
        ("assistant", "Use FastAPI."),
    ]
    assert "Current" not in second.format_context("session-1", "other")
    second.close()


def test_memory_is_bounded_and_trimmed(tmp_path):
    memory = SQLiteConversationMemory(str(tmp_path / "memory.db"), max_turns=2, max_chars=10)

    memory.append("s", "code", "user", "123456789012345")
    memory.append("s", "code", "assistant", "abcdefghijklm")
    memory.append("s", "code", "user", "third")
    memory.append("s", "code", "assistant", "fourth")

    assert memory.recent("s", "code") == [
        ("user", "third"),
        ("assistant", "fourth"),
    ]
    memory.close()


def test_memory_clear_can_scope_to_agent(tmp_path):
    memory = SQLiteConversationMemory(str(tmp_path / "memory.db"))
    memory.append("s", "code", "user", "code work")
    memory.append("s", "dsa", "user", "dsa work")

    assert memory.clear("s", "code") == 1
    assert memory.recent("s", "code") == []
    assert memory.recent("s", "dsa") == [("user", "dsa work")]
    assert memory.clear("s") == 1
    memory.close()


def test_task_store_reopens_with_same_task_data(tmp_path):
    path = tmp_path / "tasks.db"
    store = SQLiteTaskStore(str(path))
    task = Task(
        id="task-1",
        sessionId="session-1",
        status=TaskStatus(state=TaskState.COMPLETED),
        history=[],
    )
    store.save_task(task)
    store.close()

    reopened = SQLiteTaskStore(str(path))
    loaded = reopened.load_tasks()
    assert loaded["task-1"].status.state == TaskState.COMPLETED
    reopened.close()


def test_memory_redacts_common_credentials(tmp_path):
    memory = SQLiteConversationMemory(str(tmp_path / "memory.db"))
    memory.append(
        "s",
        "code",
        "user",
        "Authorization: Bearer super-secret-token api_key=top-secret",
    )

    stored = memory.recent("s", "code")[0][1]
    assert "super-secret-token" not in stored
    assert "top-secret" not in stored
    assert "<redacted>" in stored
    memory.close()


def test_memory_retention_removes_expired_records(tmp_path):
    memory = SQLiteConversationMemory(
        str(tmp_path / "memory.db"),
        retention_days=1,
    )
    memory.append("fresh", "code", "user", "keep this")

    memory.connection.execute(
        "UPDATE conversation_turns SET created_at = ? WHERE session_id = ?",
        ("2000-01-01T00:00:00+00:00", "expired"),
    )
    memory.append("expired", "code", "user", "remove this")
    memory.connection.execute(
        "UPDATE conversation_turns SET created_at = ? WHERE session_id = ?",
        ("2000-01-01T00:00:00+00:00", "expired"),
    )
    memory.connection.commit()

    assert memory.purge_expired() == 1
    assert memory.recent("expired", "code") == []
    assert memory.recent("fresh", "code") == [("user", "keep this")]
    memory.close()


def test_agent_does_not_duplicate_sqlite_context_during_active_session(tmp_path):
    from types import SimpleNamespace

    from app.agents.base import BaseAgent

    class ActiveGraph:
        def get_state(self, _config):
            return SimpleNamespace(values={"messages": [{"role": "user", "content": "old"}]})

    agent = BaseAgent.__new__(BaseAgent)
    agent.graph = ActiveGraph()
    agent.memory_store = SQLiteConversationMemory(str(tmp_path / "memory.db"))

    assert agent._prepare_query("new request", "s", {"configurable": {"thread_id": "s"}}) == (
        "new request"
    )
    agent.memory_store.close()


def test_task_store_ping(tmp_path):
    store = SQLiteTaskStore(str(tmp_path / "tasks.db"))
    assert store.ping() is True
    store.close()
