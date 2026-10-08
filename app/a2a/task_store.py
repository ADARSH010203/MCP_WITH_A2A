"""Persistent storage for A2A task state using SQLite."""

import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.a2a.models import PushNotificationConfig, Task, TaskState


class SQLiteTaskStore:
    """Small SQLite store for durable task and callback configuration state."""

    def __init__(self, path: str) -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        self.connection = sqlite3.connect(
            path,
            check_same_thread=False,
            timeout=10,
        )
        self._lock = threading.RLock()
        with self._lock:
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA busy_timeout=10000")
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
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_leases (
                    task_id TEXT PRIMARY KEY,
                    worker_id TEXT NOT NULL,
                    lease_until REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self.connection.commit()

    def ping(self) -> bool:
        """Check that the task database connection is usable."""
        try:
            with self._lock:
                self.connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def load_task(self, task_id: str) -> Task | None:
        """Load one task directly from durable storage."""
        with self._lock:
            row = self.connection.execute(
                "SELECT payload FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return Task.model_validate_json(row[0])

    def claim_task(
        self,
        task_id: str,
        worker_id: str,
        lease_seconds: float,
    ) -> bool:
        """Atomically claim a task until the lease expires."""
        if not worker_id:
            raise ValueError("worker_id is required")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")

        now = time.time()
        lease_until = now + lease_seconds

        with self._lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                row = self.connection.execute(
                    "SELECT worker_id, lease_until FROM task_leases WHERE task_id = ?",
                    (task_id,),
                ).fetchone()

                if row is not None:
                    current_worker, current_until = row
                    if current_worker != worker_id and float(current_until) > now:
                        self.connection.rollback()
                        return False

                self.connection.execute(
                    """
                    INSERT INTO task_leases (
                        task_id,
                        worker_id,
                        lease_until,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        worker_id=excluded.worker_id,
                        lease_until=excluded.lease_until,
                        updated_at=excluded.updated_at
                    """,
                    (task_id, worker_id, lease_until, now),
                )
                self.connection.commit()
                return True
            except Exception:
                self.connection.rollback()
                raise

    def renew_task_lease(
        self,
        task_id: str,
        worker_id: str,
        lease_seconds: float,
    ) -> bool:
        """Extend a lease only when this worker still owns it."""
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")

        now = time.time()
        lease_until = now + lease_seconds
        with self._lock:
            cursor = self.connection.execute(
                """
                UPDATE task_leases
                SET lease_until = ?, updated_at = ?
                WHERE task_id = ? AND worker_id = ?
                """,
                (lease_until, now, task_id, worker_id),
            )
            self.connection.commit()
            return cursor.rowcount == 1

    def release_task(
        self,
        task_id: str,
        worker_id: str,
    ) -> bool:
        """Release a task lease only when owned by the current worker."""
        with self._lock:
            cursor = self.connection.execute(
                """
                DELETE FROM task_leases
                WHERE task_id = ? AND worker_id = ?
                """,
                (task_id, worker_id),
            )
            self.connection.commit()
            return cursor.rowcount == 1

    def task_claimed_by_other(
        self,
        task_id: str,
        worker_id: str,
    ) -> bool:
        """Return whether a non-expired lease belongs to another worker."""
        now = time.time()
        with self._lock:
            row = self.connection.execute(
                """
                SELECT worker_id, lease_until
                FROM task_leases
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()

        return bool(
            row is not None
            and row[0] != worker_id
            and float(row[1]) > now
        )

    def list_recoverable_tasks(self, limit: int) -> list[Task]:
        """Return submitted/working tasks with no live worker lease."""
        if limit < 1:
            raise ValueError("limit must be positive")
        now = time.time()
        with self._lock:
            rows = self.connection.execute(
                "SELECT id, payload FROM tasks"
            ).fetchall()
            leases = {
                task_id: float(lease_until)
                for task_id, lease_until in self.connection.execute(
                    "SELECT task_id, lease_until FROM task_leases"
                ).fetchall()
            }

        recoverable: list[Task] = []
        for task_id, payload in rows:
            if leases.get(task_id, 0.0) > now:
                continue
            try:
                task = Task.model_validate_json(payload)
            except ValueError:
                continue
            if task.status.state not in {TaskState.SUBMITTED, TaskState.WORKING}:
                continue
            recoverable.append(task)

        recoverable.sort(
            key=lambda item: item.status.timestamp,
        )
        return recoverable[:limit]

    def purge_expired_leases(self) -> int:
        """Delete expired task leases."""
        now = time.time()
        with self._lock:
            cursor = self.connection.execute(
                "DELETE FROM task_leases WHERE lease_until <= ?",
                (now,),
            )
            self.connection.commit()
            return cursor.rowcount

    def load_tasks(self) -> dict[str, Task]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT id, payload FROM tasks"
            ).fetchall()
        return {
            task_id: Task.model_validate_json(payload)
            for task_id, payload in rows
        }

    def load_push_notification_configs(
        self,
    ) -> dict[str, PushNotificationConfig]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT task_id, payload FROM push_notification_configs"
            ).fetchall()
        return {
            task_id: PushNotificationConfig.model_validate_json(payload)
            for task_id, payload in rows
        }

    def create_task_if_absent(self, task: Task) -> tuple[Task, bool]:
        """Atomically create a task, returning the durable winner on races."""
        payload = task.model_dump_json()
        with self._lock:
            cursor = self.connection.execute(
                """
                INSERT OR IGNORE INTO tasks (id, payload)
                VALUES (?, ?)
                """,
                (task.id, payload),
            )
            self.connection.commit()

            if cursor.rowcount == 1:
                return task, True

            row = self.connection.execute(
                "SELECT payload FROM tasks WHERE id = ?",
                (task.id,),
            ).fetchone()

        if row is None:
            raise RuntimeError(f"Task {task.id} disappeared after creation race")
        return Task.model_validate_json(row[0]), False

    def save_task(self, task: Task) -> None:
        payload = task.model_dump_json()
        with self._lock:
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
        with self._lock:
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

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        terminal_states = {
            "completed",
            "failed",
            "canceled",
            "input-required",
        }

        with self._lock:
            rows = self.connection.execute(
                "SELECT id, payload FROM tasks"
            ).fetchall()

            expired_ids: list[str] = []
            for task_id, payload in rows:
                try:
                    task = Task.model_validate_json(payload)
                except ValueError:
                    continue

                if (
                    task.status.state.value in terminal_states
                    and task.status.timestamp < cutoff
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
        with self._lock:
            self.connection.close()
