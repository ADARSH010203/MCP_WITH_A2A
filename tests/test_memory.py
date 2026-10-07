"""Persistent memory and SQLite infrastructure tests."""

from app.a2a.models import Task, TaskState, TaskStatus
from app.a2a.task_store import SQLiteTaskStore
from app.memory.context import use_memory_principal
from app.memory.sqlite_memory import SQLiteConversationMemory


def test_memory_survives_store_reopen(tmp_path):
    path = tmp_path / "memory.db"

    first = SQLiteConversationMemory(str(path), max_turns=4, max_chars=100, namespace_secret="test-secret")
    first.append("tenant-a", "session-1", "code", "user", "Build a Python API")
    first.append("tenant-a", "session-1", "code", "assistant", "Use FastAPI.")
    first.close()

    second = SQLiteConversationMemory(str(path), max_turns=4, max_chars=100, namespace_secret="test-secret")
    assert second.recent("tenant-a", "session-1", "code") == [
        ("user", "Build a Python API"),
        ("assistant", "Use FastAPI."),
    ]
    assert "Current" not in second.format_context("tenant-a", "session-1", "other")
    second.close()


def test_memory_is_bounded_and_trimmed(tmp_path):
    memory = SQLiteConversationMemory(str(tmp_path / "memory.db"), max_turns=2, max_chars=10, namespace_secret="test-secret")

    memory.append("tenant-a", "s", "code", "user", "123456789012345")
    memory.append("tenant-a", "s", "code", "assistant", "abcdefghijklm")
    memory.append("tenant-a", "s", "code", "user", "third")
    memory.append("tenant-a", "s", "code", "assistant", "fourth")

    assert memory.recent("tenant-a", "s", "code") == [
        ("user", "third"),
        ("assistant", "fourth"),
    ]
    memory.close()


def test_memory_clear_can_scope_to_agent(tmp_path):
    memory = SQLiteConversationMemory(str(tmp_path / "memory.db"), namespace_secret="test-secret")
    memory.append("tenant-a", "s", "code", "user", "code work")
    memory.append("tenant-a", "s", "dsa", "user", "dsa work")

    assert memory.clear("tenant-a", "s", "code") == 1
    assert memory.recent("tenant-a", "s", "code") == []
    assert memory.recent("tenant-a", "s", "dsa") == [("user", "dsa work")]
    assert memory.clear("tenant-a", "s") == 1
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
    memory = SQLiteConversationMemory(str(tmp_path / "memory.db"), namespace_secret="test-secret")
    memory.append(
        "tenant-a",
        "s",
        "code",
        "user",
        "Authorization: Bearer super-secret-token api_key=top-secret",
    )

    stored = memory.recent("tenant-a", "s", "code")[0][1]
    assert "super-secret-token" not in stored
    assert "top-secret" not in stored
    assert "<redacted>" in stored
    memory.close()


def test_memory_retention_removes_expired_records(tmp_path):
    memory = SQLiteConversationMemory(
        str(tmp_path / "memory.db"),
        retention_days=1,
        namespace_secret="test-secret",
    )
    memory.append("tenant-a", "fresh", "code", "user", "keep this")

    expired_scope = memory._scope(
        "tenant-a",
        "expired",
        "code",
    ).session_key(memory.namespace_secret)
    memory.connection.execute(
        "UPDATE conversation_turns SET created_at = ? WHERE session_scope_key = ?",
        ("2000-01-01T00:00:00+00:00", expired_scope),
    )
    memory.append("tenant-a", "expired", "code", "user", "remove this")
    memory.connection.execute(
        "UPDATE conversation_turns SET created_at = ? WHERE session_id = ?",
        ("2000-01-01T00:00:00+00:00", "expired"),
    )
    memory.connection.commit()

    assert memory.purge_expired() == 1
    assert memory.recent("tenant-a", "expired", "code") == []
    assert memory.recent("tenant-a", "fresh", "code") == [("user", "keep this")]
    memory.close()


def test_agent_does_not_duplicate_sqlite_context_during_active_session(tmp_path):
    from types import SimpleNamespace

    from app.agents.base import BaseAgent

    class ActiveGraph:
        def get_state(self, _config):
            return SimpleNamespace(values={"messages": [{"role": "user", "content": "old"}]})

    agent = BaseAgent.__new__(BaseAgent)
    agent.graph = ActiveGraph()
    agent.memory_store = SQLiteConversationMemory(str(tmp_path / "memory.db"), namespace_secret="test-secret")

    assert agent._prepare_query("new request", "s", {"configurable": {"thread_id": "s"}}) == (
        "new request"
    )
    agent.memory_store.close()


def test_task_store_ping(tmp_path):
    store = SQLiteTaskStore(str(tmp_path / "tasks.db"))
    assert store.ping() is True
    store.close()


def test_memory_isolated_by_principal_and_agent(tmp_path):
    memory = SQLiteConversationMemory(
        str(tmp_path / "memory.db"),
        namespace_secret="test-secret",
    )
    memory.append("tenant-a", "shared-session", "code", "user", "private code context")
    memory.append("tenant-b", "shared-session", "code", "user", "other tenant context")
    memory.append("tenant-a", "shared-session", "dsa", "user", "other agent context")

    assert memory.recent("tenant-a", "shared-session", "code") == [
        ("user", "private code context")
    ]
    assert memory.recent("tenant-b", "shared-session", "code") == [
        ("user", "other tenant context")
    ]
    assert memory.recent("tenant-a", "shared-session", "dsa") == [
        ("user", "other agent context")
    ]
    memory.close()


def test_memory_scope_keys_do_not_store_raw_identity(tmp_path):
    memory = SQLiteConversationMemory(
        str(tmp_path / "memory.db"),
        namespace_secret="test-secret",
    )
    memory.append("tenant-a", "sensitive-session", "code", "user", "secret context")

    columns = [row[1] for row in memory.connection.execute(
        "PRAGMA table_info(conversation_turns)"
    ).fetchall()]
    row = memory.connection.execute(
        "SELECT session_scope_key, scope_key FROM conversation_turns"
    ).fetchone()

    assert "session_id" not in columns
    assert "agent_type" not in columns
    assert "tenant-a" not in row
    assert "sensitive-session" not in row
    assert "code" not in row
    memory.close()


def test_memory_scope_context_switches_principal(tmp_path):
    memory = SQLiteConversationMemory(
        str(tmp_path / "memory.db"),
        namespace_secret="test-secret",
    )
    with use_memory_principal("tenant-a"):
        memory.append("tenant-a", "s", "code", "user", "A")
    with use_memory_principal("tenant-b"):
        memory.append("tenant-b", "s", "code", "user", "B")

    assert memory.recent("tenant-a", "s", "code") == [("user", "A")]
    assert memory.recent("tenant-b", "s", "code") == [("user", "B")]
    memory.close()
