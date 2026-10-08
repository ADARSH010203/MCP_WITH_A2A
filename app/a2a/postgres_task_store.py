"""PostgreSQL-backed durable A2A task storage."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import psycopg

from app.a2a.models import PushNotificationConfig, Task, TaskState


class PostgresTaskStore:
    """Transactional task store for multi-process and multi-host deployments."""

    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise ValueError("A2A_TASK_DATABASE_URL is required for PostgreSQL storage.")

        self.database_url = database_url
        self.connection = psycopg.connect(
            database_url,
            connect_timeout=5,
        )
        self.connection.autocommit = True
        self._lock = threading.RLock()
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS push_notification_configs (
                    task_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS task_leases (
                    task_id TEXT PRIMARY KEY,
                    worker_id TEXT NOT NULL,
                    lease_until DOUBLE PRECISION NOT NULL,
                    updated_at DOUBLE PRECISION NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_leases_expiry
                ON task_leases (lease_until)
                """
            )

    def ping(self) -> bool:
        try:
            with self._lock, self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return True
        except psycopg.Error:
            return False

    def load_tasks(self) -> dict[str, Task]:
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute("SELECT id, payload FROM tasks")
            rows = cursor.fetchall()
        return {
            task_id: Task.model_validate_json(payload)
            for task_id, payload in rows
        }

    def load_task(self, task_id: str) -> Task | None:
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload FROM tasks WHERE id = %s",
                (task_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return Task.model_validate_json(row[0])

    def create_task_if_absent(self, task: Task) -> tuple[Task, bool]:
        payload = task.model_dump_json()
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tasks (id, payload)
                VALUES (%s, %s)
                ON CONFLICT (id) DO NOTHING
                RETURNING id, payload
                """,
                (task.id, payload),
            )
            row = cursor.fetchone()
            if row is not None:
                return task, True

            cursor.execute(
                "SELECT payload FROM tasks WHERE id = %s",
                (task.id,),
            )
            existing = cursor.fetchone()

        if existing is None:
            raise RuntimeError(
                f"Task {task.id} disappeared after the creation race."
            )
        return Task.model_validate_json(existing[0]), False

    def save_task(self, task: Task) -> None:
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tasks (id, payload)
                VALUES (%s, %s)
                ON CONFLICT (id)
                DO UPDATE SET payload = EXCLUDED.payload
                """,
                (task.id, task.model_dump_json()),
            )

    def load_push_notification_configs(
        self,
    ) -> dict[str, PushNotificationConfig]:
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT task_id, payload FROM push_notification_configs"
            )
            rows = cursor.fetchall()
        return {
            task_id: PushNotificationConfig.model_validate_json(payload)
            for task_id, payload in rows
        }

    def save_push_notification_config(
        self,
        task_id: str,
        config: PushNotificationConfig,
    ) -> None:
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO push_notification_configs (task_id, payload)
                VALUES (%s, %s)
                ON CONFLICT (task_id)
                DO UPDATE SET payload = EXCLUDED.payload
                """,
                (task_id, config.model_dump_json()),
            )

    def purge_expired(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0

        cutoff = datetime.now(timezone.utc)
        terminal_states = (
            "completed",
            "failed",
            "canceled",
            "input-required",
        )

        with self._lock, self.connection.cursor() as cursor:
            cursor.execute("SELECT id, payload FROM tasks")
            rows = cursor.fetchall()

            expired_ids: list[str] = []
            for task_id, payload in rows:
                try:
                    task = Task.model_validate_json(payload)
                except ValueError:
                    continue
                if (
                    task.status.state.value in terminal_states
                    and task.status.timestamp < cutoff - timedelta(days=retention_days)
                ):
                    expired_ids.append(task_id)

            if not expired_ids:
                return 0

            cursor.executemany(
                "DELETE FROM tasks WHERE id = %s",
                [(task_id,) for task_id in expired_ids],
            )
            cursor.executemany(
                "DELETE FROM push_notification_configs WHERE task_id = %s",
                [(task_id,) for task_id in expired_ids],
            )
        return len(expired_ids)

    def list_recoverable_tasks(self, limit: int) -> list[Task]:
        if limit < 1:
            raise ValueError("limit must be positive")

        now = time.time()
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT t.payload
                FROM tasks AS t
                LEFT JOIN task_leases AS l
                  ON l.task_id = t.id
                WHERE (l.task_id IS NULL OR l.lease_until <= %s)
                ORDER BY (t.payload::jsonb->'status'->>'timestamp')::timestamptz
                LIMIT %s
                """,
                (now, limit),
            )
            rows = cursor.fetchall()

        tasks: list[Task] = []
        for (payload,) in rows:
            try:
                task = Task.model_validate_json(payload)
            except ValueError:
                continue
            if task.status.state in {TaskState.SUBMITTED, TaskState.WORKING}:
                tasks.append(task)
        return tasks

    def purge_expired_leases(self) -> int:
        now = time.time()
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM task_leases WHERE lease_until <= %s",
                (now,),
            )
            return cursor.rowcount

    def claim_task(
        self,
        task_id: str,
        worker_id: str,
        lease_seconds: float,
    ) -> bool:
        if not worker_id:
            raise ValueError("worker_id is required")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")

        now = time.time()
        lease_until = now + lease_seconds
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO task_leases (
                    task_id,
                    worker_id,
                    lease_until,
                    updated_at
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (task_id)
                DO UPDATE SET
                    worker_id = EXCLUDED.worker_id,
                    lease_until = EXCLUDED.lease_until,
                    updated_at = EXCLUDED.updated_at
                WHERE task_leases.worker_id = EXCLUDED.worker_id
                   OR task_leases.lease_until <= EXCLUDED.updated_at
                RETURNING task_id
                """,
                (task_id, worker_id, lease_until, now),
            )
            return cursor.fetchone() is not None

    def renew_task_lease(
        self,
        task_id: str,
        worker_id: str,
        lease_seconds: float,
    ) -> bool:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")

        now = time.time()
        lease_until = now + lease_seconds
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE task_leases
                SET lease_until = %s, updated_at = %s
                WHERE task_id = %s
                  AND worker_id = %s
                  AND lease_until > %s
                """,
                (lease_until, now, task_id, worker_id, now),
            )
            return cursor.rowcount == 1

    def release_task(self, task_id: str, worker_id: str) -> bool:
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM task_leases
                WHERE task_id = %s AND worker_id = %s
                """,
                (task_id, worker_id),
            )
            return cursor.rowcount == 1

    def task_claimed_by_other(
        self,
        task_id: str,
        worker_id: str,
    ) -> bool:
        now = time.time()
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT worker_id, lease_until
                FROM task_leases
                WHERE task_id = %s
                """,
                (task_id,),
            )
            row = cursor.fetchone()

        return bool(
            row is not None
            and row[0] != worker_id
            and float(row[1]) > now
        )

    def close(self) -> None:
        with self._lock:
            self.connection.close()
