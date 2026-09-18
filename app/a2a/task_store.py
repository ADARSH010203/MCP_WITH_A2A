"""Persistent storage for A2A task state using SQLite."""

import sqlite3
from pathlib import Path

from app.a2a.models import PushNotificationConfig, Task


class SQLiteTaskStore:
    """Small SQLite store for durable task and callback configuration state."""

    def __init__(self, path: str) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        self.connection = sqlite3.connect(
            path,
            check_same_thread=False,
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS push_notification_configs (
                task_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def load_tasks(self) -> dict[str, Task]:
        rows = self.connection.execute("SELECT id, payload FROM tasks").fetchall()
        return {task_id: Task.model_validate_json(payload) for task_id, payload in rows}

    def load_push_notification_configs(
        self,
    ) -> dict[str, PushNotificationConfig]:
        rows = self.connection.execute(
            "SELECT task_id, payload FROM push_notification_configs"
        ).fetchall()
        return {
            task_id: PushNotificationConfig.model_validate_json(payload)
            for task_id, payload in rows
        }

    def save_task(self, task: Task) -> None:
        payload = task.model_dump_json()
        self.connection.execute(
            """
            INSERT INTO tasks (id, payload)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET payload=excluded.payload
            """,
            (task.id, payload),
        )
        self.connection.commit()

    def save_push_notification_config(
        self,
        task_id: str,
        config: PushNotificationConfig,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO push_notification_configs (task_id, payload)
            VALUES (?, ?)
            ON CONFLICT(task_id) DO UPDATE SET payload=excluded.payload
            """,
            (task_id, config.model_dump_json()),
        )
        self.connection.commit()

    def purge_expired(self, retention_days: int) -> int:
        """Delete old terminal tasks and their callback configuration."""
        if retention_days <= 0:
            return 0

        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        terminal_states = {
            "completed",
            "failed",
            "canceled",
            "input-required",
        }

        rows = self.connection.execute("SELECT id, payload FROM tasks").fetchall()
        expired_ids: list[str] = []
        for task_id, payload in rows:
            try:
                task = Task.model_validate_json(payload)
            except ValueError:
                continue

            timestamp = task.status.timestamp
            if (
                task.status.state.value in terminal_states
                and timestamp < cutoff
            ):
                expired_ids.append(task_id)

        if not expired_ids:
            return 0

        self.connection.executemany(
            "DELETE FROM tasks WHERE id = ?",
            [(task_id,) for task_id in expired_ids],
        )
        self.connection.executemany(
            "DELETE FROM push_notification_configs WHERE task_id = ?",
            [(task_id,) for task_id in expired_ids],
        )
        self.connection.commit()
        return len(expired_ids)

    def close(self) -> None:
        self.connection.close()
