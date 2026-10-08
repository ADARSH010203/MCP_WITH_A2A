from types import SimpleNamespace

import pytest

from app.a2a.task_store import SQLiteTaskStore
from app.a2a.task_store_factory import build_task_store


def test_factory_builds_sqlite_store(monkeypatch, tmp_path):
    import app.a2a.task_store_factory as module

    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(
            a2a_task_store_backend="sqlite",
            a2a_task_db_path=str(tmp_path / "tasks.db"),
            a2a_task_database_url="",
        ),
    )

    store = build_task_store()
    assert isinstance(store, SQLiteTaskStore)
    assert store.ping() is True
    store.close()


def test_factory_rejects_postgres_without_database_url(monkeypatch):
    import app.a2a.task_store_factory as module

    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(
            a2a_task_store_backend="postgres",
            a2a_task_db_path=":memory:",
            a2a_task_database_url="",
        ),
    )

    with pytest.raises(ValueError, match="A2A_TASK_DATABASE_URL"):
        build_task_store()


def test_factory_rejects_unknown_backend(monkeypatch):
    import app.a2a.task_store_factory as module

    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(
            a2a_task_store_backend="oracle",
            a2a_task_db_path=":memory:",
            a2a_task_database_url="",
        ),
    )

    with pytest.raises(ValueError, match="sqlite.*postgres"):
        build_task_store()
