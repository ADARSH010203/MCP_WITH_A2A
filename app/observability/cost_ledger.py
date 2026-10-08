"""Durable cost attribution and budget reporting."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg

from app.config.settings import settings
from app.observability.cost import TokenUsage


class CostLedgerError(RuntimeError):
    """Raised when cost-ledger storage cannot be initialized or used."""


@dataclass(frozen=True)
class CostLedgerEntry:
    """One completed top-level task cost record."""

    task_key: str
    principal_id: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    status: str
    agents: tuple[str, ...]
    recorded_at: datetime

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class CostTotals:
    """Aggregated usage over a requested reporting window."""

    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    tasks: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 8),
            "tasks": self.tasks,
        }


class CostLedger:
    """Backend-neutral durable cost attribution contract."""

    def record(self, entry: CostLedgerEntry) -> bool:
        raise NotImplementedError

    def totals(
        self,
        principal_id: str,
        *,
        since: datetime | None = None,
    ) -> CostTotals:
        raise NotImplementedError

    def ping(self) -> bool:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class _SQLiteCostLedger(CostLedger):
    def __init__(self, path: str, namespace_secret: str) -> None:
        if not namespace_secret:
            raise CostLedgerError("A memory namespace secret is required.")

        self.path = path
        self.namespace_secret = namespace_secret
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        self.connection = sqlite3.connect(
            path,
            check_same_thread=False,
            timeout=10,
        )
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=10000")
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cost_ledger (
                    task_key TEXT PRIMARY KEY,
                    principal_key TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL,
                    status TEXT NOT NULL,
                    agents_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cost_ledger_principal_time
                ON cost_ledger(principal_key, recorded_at)
                """
            )
            self.connection.commit()

    def _principal_key(self, principal_id: str) -> str:
        return hmac.new(
            self.namespace_secret.encode("utf-8"),
            principal_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def record(self, entry: CostLedgerEntry) -> bool:
        principal_key = self._principal_key(entry.principal_id)
        with self._lock:
            cursor = self.connection.execute(
                """
                INSERT OR IGNORE INTO cost_ledger (
                    task_key,
                    principal_key,
                    input_tokens,
                    output_tokens,
                    estimated_cost_usd,
                    status,
                    agents_json,
                    recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.task_key,
                    principal_key,
                    entry.input_tokens,
                    entry.output_tokens,
                    entry.estimated_cost_usd,
                    entry.status,
                    json.dumps(entry.agents, separators=(",", ":")),
                    entry.recorded_at.astimezone(timezone.utc).isoformat(),
                ),
            )
            self.connection.commit()
            return cursor.rowcount == 1

    def totals(
        self,
        principal_id: str,
        *,
        since: datetime | None = None,
    ) -> CostTotals:
        principal_key = self._principal_key(principal_id)
        query = (
            "SELECT COALESCE(SUM(input_tokens), 0), "
            "COALESCE(SUM(output_tokens), 0), "
            "COALESCE(SUM(estimated_cost_usd), 0), "
            "COUNT(*) FROM cost_ledger WHERE principal_key = ?"
        )
        params: list[Any] = [principal_key]
        if since is not None:
            query += " AND recorded_at >= ?"
            params.append(since.astimezone(timezone.utc).isoformat())

        with self._lock:
            row = self.connection.execute(query, tuple(params)).fetchone()

        return CostTotals(
            input_tokens=int(row[0]),
            output_tokens=int(row[1]),
            estimated_cost_usd=float(row[2]),
            tasks=int(row[3]),
        )

    def ping(self) -> bool:
        try:
            with self._lock:
                self.connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        with self._lock:
            self.connection.close()


class _PostgresCostLedger(CostLedger):
    def __init__(self, database_url: str, namespace_secret: str) -> None:
        if not database_url.strip():
            raise CostLedgerError("PostgreSQL database URL is required.")
        if not namespace_secret:
            raise CostLedgerError("A memory namespace secret is required.")

        self.database_url = database_url
        self.namespace_secret = namespace_secret
        self.connection = psycopg.connect(
            database_url,
            connect_timeout=5,
        )
        self.connection.autocommit = True
        self._lock = threading.RLock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cost_ledger (
                    task_key TEXT PRIMARY KEY,
                    principal_key TEXT NOT NULL,
                    input_tokens BIGINT NOT NULL,
                    output_tokens BIGINT NOT NULL,
                    estimated_cost_usd DOUBLE PRECISION NOT NULL,
                    status TEXT NOT NULL,
                    agents_json TEXT NOT NULL,
                    recorded_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cost_ledger_principal_time
                ON cost_ledger(principal_key, recorded_at)
                """
            )

    def _principal_key(self, principal_id: str) -> str:
        return hmac.new(
            self.namespace_secret.encode("utf-8"),
            principal_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def record(self, entry: CostLedgerEntry) -> bool:
        principal_key = self._principal_key(entry.principal_id)
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cost_ledger (
                    task_key,
                    principal_key,
                    input_tokens,
                    output_tokens,
                    estimated_cost_usd,
                    status,
                    agents_json,
                    recorded_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (task_key) DO NOTHING
                """,
                (
                    entry.task_key,
                    principal_key,
                    entry.input_tokens,
                    entry.output_tokens,
                    entry.estimated_cost_usd,
                    entry.status,
                    json.dumps(entry.agents, separators=(",", ":")),
                    entry.recorded_at.astimezone(timezone.utc),
                ),
            )
            return cursor.rowcount == 1

    def totals(
        self,
        principal_id: str,
        *,
        since: datetime | None = None,
    ) -> CostTotals:
        principal_key = self._principal_key(principal_id)
        query = (
            "SELECT COALESCE(SUM(input_tokens), 0), "
            "COALESCE(SUM(output_tokens), 0), "
            "COALESCE(SUM(estimated_cost_usd), 0), "
            "COUNT(*) FROM cost_ledger WHERE principal_key = %s"
        )
        params: list[Any] = [principal_key]
        if since is not None:
            query += " AND recorded_at >= %s"
            params.append(since.astimezone(timezone.utc))

        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            row = cursor.fetchone()

        return CostTotals(
            input_tokens=int(row[0]),
            output_tokens=int(row[1]),
            estimated_cost_usd=float(row[2]),
            tasks=int(row[3]),
        )

    def ping(self) -> bool:
        try:
            with self._lock, self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return True
        except psycopg.Error:
            return False

    def close(self) -> None:
        with self._lock:
            self.connection.close()


def build_cost_ledger() -> CostLedger:
    """Build the ledger on the same durable backend as task state."""
    secret = settings.a2a_memory_namespace_secret
    if not secret:
        raise CostLedgerError(
            "A2A_MEMORY_NAMESPACE_SECRET is required for cost attribution."
        )

    if settings.a2a_task_store_backend == "postgres":
        return _PostgresCostLedger(
            settings.a2a_task_database_url,
            secret,
        )

    return _SQLiteCostLedger(
        settings.a2a_task_db_path,
        secret,
    )


class CostGovernance:
    """Record task usage and report daily/monthly principal budgets."""

    def __init__(self, ledger: CostLedger) -> None:
        self.ledger = ledger

    @staticmethod
    def _period_start(period: str, now: datetime) -> datetime:
        utc_now = now.astimezone(timezone.utc)
        if period == "day":
            return utc_now.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        if period == "month":
            return utc_now.replace(
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
        raise ValueError("period must be 'day' or 'month'")

    def record(
        self,
        *,
        task_key: str,
        principal_id: str,
        usage: TokenUsage,
        estimated_cost_usd: float,
        status: str,
        agents: tuple[str, ...],
        recorded_at: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = recorded_at or datetime.now(timezone.utc)
        inserted = self.ledger.record(
            CostLedgerEntry(
                task_key=task_key,
                principal_id=principal_id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                estimated_cost_usd=estimated_cost_usd,
                status=status,
                agents=agents,
                recorded_at=timestamp,
            )
        )

        daily = self.ledger.totals(
            principal_id,
            since=self._period_start("day", timestamp),
        )
        monthly = self.ledger.totals(
            principal_id,
            since=self._period_start("month", timestamp),
        )

        return {
            "recorded": inserted,
            "daily": daily.to_dict(),
            "monthly": monthly.to_dict(),
        }

    def report(self, principal_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "principal_scoped": True,
            "daily": self.ledger.totals(
                principal_id,
                since=self._period_start("day", now),
            ).to_dict(),
            "monthly": self.ledger.totals(
                principal_id,
                since=self._period_start("month", now),
            ).to_dict(),
        }
