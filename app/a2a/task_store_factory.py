"""Select the configured durable task-store backend."""

from __future__ import annotations

from app.a2a.postgres_task_store import PostgresTaskStore
from app.a2a.store_protocol import TaskStore
from app.a2a.task_store import SQLiteTaskStore
from app.config.settings import settings


def build_task_store() -> TaskStore:
    """Create the configured durable task store."""
    backend = settings.a2a_task_store_backend

    if backend == "sqlite":
        return SQLiteTaskStore(settings.a2a_task_db_path)

    if backend == "postgres":
        if not settings.a2a_task_database_url:
            raise ValueError(
                "A2A_TASK_DATABASE_URL is required when "
                "A2A_TASK_STORE_BACKEND=postgres."
            )
        return PostgresTaskStore(settings.a2a_task_database_url)

    raise ValueError(
        "A2A_TASK_STORE_BACKEND must be either 'sqlite' or 'postgres'."
    )
