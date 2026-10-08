"""Task-store contract shared by SQLite and PostgreSQL backends."""

from __future__ import annotations

from typing import Protocol

from app.a2a.models import PushNotificationConfig, Task


class TaskStore(Protocol):
    """Minimal durable store contract required by the A2A task manager."""

    def ping(self) -> bool: ...

    def load_tasks(self) -> dict[str, Task]: ...

    def load_task(self, task_id: str) -> Task | None: ...

    def create_task_if_absent(self, task: Task) -> tuple[Task, bool]: ...

    def save_task(self, task: Task) -> None: ...

    def load_push_notification_configs(
        self,
    ) -> dict[str, PushNotificationConfig]: ...

    def save_push_notification_config(
        self,
        task_id: str,
        config: PushNotificationConfig,
    ) -> None: ...

    def purge_expired(self, retention_days: int) -> int: ...

    def purge_expired_leases(self) -> int: ...

    def claim_task(
        self,
        task_id: str,
        worker_id: str,
        lease_seconds: float,
    ) -> bool: ...

    def renew_task_lease(
        self,
        task_id: str,
        worker_id: str,
        lease_seconds: float,
    ) -> bool: ...

    def release_task(self, task_id: str, worker_id: str) -> bool: ...

    def task_claimed_by_other(
        self,
        task_id: str,
        worker_id: str,
    ) -> bool: ...

    def close(self) -> None: ...
