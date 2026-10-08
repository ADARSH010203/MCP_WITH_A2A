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

    def reserve_budget(
        self,
        *,
        principal_id: str,
        reservation_key: str,
        reserved_tokens: int,
        reserved_cost_usd: float,
        daily_token_limit: int,
        monthly_token_limit: int,
        daily_cost_limit_usd: float,
        monthly_cost_limit_usd: float,
        now: datetime,
        expires_at: datetime,
    ) -> bool:
        raise NotImplementedError

    def release_budget(self, reservation_key: str) -> None:
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
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cost_budget_reservations (
                    reservation_key TEXT PRIMARY KEY,
                    principal_key TEXT NOT NULL,
                    reserved_tokens INTEGER NOT NULL,
                    reserved_cost_usd REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cost_reservations_principal_expiry
                ON cost_budget_reservations(principal_key, expires_at)
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

    def reserve_budget(
        self,
        *,
        principal_id: str,
        reservation_key: str,
        reserved_tokens: int,
        reserved_cost_usd: float,
        daily_token_limit: int,
        monthly_token_limit: int,
        daily_cost_limit_usd: float,
        monthly_cost_limit_usd: float,
        now: datetime,
        expires_at: datetime,
    ) -> bool:
        principal_key = self._principal_key(principal_id)
        now_value = now.astimezone(timezone.utc).isoformat()
        expiry_value = expires_at.astimezone(timezone.utc).isoformat()
        daily_start = now.astimezone(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        monthly_start = now.astimezone(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                self.connection.execute(
                    "DELETE FROM cost_budget_reservations WHERE expires_at <= ?",
                    (now_value,),
                )
                daily = self.connection.execute(
                    """
                    SELECT COALESCE(SUM(input_tokens + output_tokens), 0),
                           COALESCE(SUM(estimated_cost_usd), 0)
                    FROM cost_ledger
                    WHERE principal_key = ? AND recorded_at >= ?
                    """,
                    (principal_key, daily_start),
                ).fetchone()
                monthly = self.connection.execute(
                    """
                    SELECT COALESCE(SUM(input_tokens + output_tokens), 0),
                           COALESCE(SUM(estimated_cost_usd), 0)
                    FROM cost_ledger
                    WHERE principal_key = ? AND recorded_at >= ?
                    """,
                    (principal_key, monthly_start),
                ).fetchone()
                reserved = self.connection.execute(
                    """
                    SELECT COALESCE(SUM(reserved_tokens), 0),
                           COALESCE(SUM(reserved_cost_usd), 0)
                    FROM cost_budget_reservations
                    WHERE principal_key = ? AND expires_at > ?
                    """,
                    (principal_key, now_value),
                ).fetchone()

                daily_tokens = int(daily[0]) + int(reserved[0]) + reserved_tokens
                monthly_tokens = int(monthly[0]) + int(reserved[0]) + reserved_tokens
                daily_cost = float(daily[1]) + float(reserved[1]) + reserved_cost_usd
                monthly_cost = float(monthly[1]) + float(reserved[1]) + reserved_cost_usd

                within_budget = (
                    (daily_token_limit <= 0 or daily_tokens <= daily_token_limit)
                    and (monthly_token_limit <= 0 or monthly_tokens <= monthly_token_limit)
                    and (daily_cost_limit_usd <= 0 or daily_cost <= daily_cost_limit_usd)
                    and (monthly_cost_limit_usd <= 0 or monthly_cost <= monthly_cost_limit_usd)
                )
                if not within_budget:
                    self.connection.rollback()
                    return False

                self.connection.execute(
                    """
                    INSERT INTO cost_budget_reservations (
                        reservation_key,
                        principal_key,
                        reserved_tokens,
                        reserved_cost_usd,
                        created_at,
                        expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        reservation_key,
                        principal_key,
                        reserved_tokens,
                        reserved_cost_usd,
                        now_value,
                        expiry_value,
                    ),
                )
                self.connection.commit()
                return True
            except Exception:
                self.connection.rollback()
                raise

    def release_budget(self, reservation_key: str) -> None:
        with self._lock:
            self.connection.execute(
                "DELETE FROM cost_budget_reservations WHERE reservation_key = ?",
                (reservation_key,),
            )
            self.connection.commit()

    def reserve_budget(
        self,
        *,
        principal_id: str,
        reservation_key: str,
        reserved_tokens: int,
        reserved_cost_usd: float,
        daily_token_limit: int,
        monthly_token_limit: int,
        daily_cost_limit_usd: float,
        monthly_cost_limit_usd: float,
        now: datetime,
        expires_at: datetime,
    ) -> bool:
        principal_key = self._principal_key(principal_id)
        utc_now = now.astimezone(timezone.utc)
        daily_start = utc_now.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        monthly_start = utc_now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        with self._lock, self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (principal_key,),
                )
                cursor.execute(
                    "DELETE FROM cost_budget_reservations WHERE expires_at <= %s",
                    (utc_now,),
                )
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(input_tokens + output_tokens), 0),
                           COALESCE(SUM(estimated_cost_usd), 0)
                    FROM cost_ledger
                    WHERE principal_key = %s AND recorded_at >= %s
                    """,
                    (principal_key, daily_start),
                )
                daily = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(input_tokens + output_tokens), 0),
                           COALESCE(SUM(estimated_cost_usd), 0)
                    FROM cost_ledger
                    WHERE principal_key = %s AND recorded_at >= %s
                    """,
                    (principal_key, monthly_start),
                )
                monthly = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT COALESCE(SUM(reserved_tokens), 0),
                           COALESCE(SUM(reserved_cost_usd), 0)
                    FROM cost_budget_reservations
                    WHERE principal_key = %s AND expires_at > %s
                    """,
                    (principal_key, utc_now),
                )
                reserved = cursor.fetchone()

                daily_tokens = int(daily[0]) + int(reserved[0]) + reserved_tokens
                monthly_tokens = int(monthly[0]) + int(reserved[0]) + reserved_tokens
                daily_cost = float(daily[1]) + float(reserved[1]) + reserved_cost_usd
                monthly_cost = float(monthly[1]) + float(reserved[1]) + reserved_cost_usd

                within_budget = (
                    (daily_token_limit <= 0 or daily_tokens <= daily_token_limit)
                    and (monthly_token_limit <= 0 or monthly_tokens <= monthly_token_limit)
                    and (daily_cost_limit_usd <= 0 or daily_cost <= daily_cost_limit_usd)
                    and (monthly_cost_limit_usd <= 0 or monthly_cost <= monthly_cost_limit_usd)
                )
                if not within_budget:
                    return False

                cursor.execute(
                    """
                    INSERT INTO cost_budget_reservations (
                        reservation_key,
                        principal_key,
                        reserved_tokens,
                        reserved_cost_usd,
                        created_at,
                        expires_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        reservation_key,
                        principal_key,
                        reserved_tokens,
                        reserved_cost_usd,
                        utc_now,
                        expires_at.astimezone(timezone.utc),
                    ),
                )
                return True

    def release_budget(self, reservation_key: str) -> None:
        with self._lock, self.connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM cost_budget_reservations WHERE reservation_key = %s",
                (reservation_key,),
            )

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
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cost_budget_reservations (
                    reservation_key TEXT PRIMARY KEY,
                    principal_key TEXT NOT NULL,
                    reserved_tokens BIGINT NOT NULL,
                    reserved_cost_usd DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cost_reservations_principal_expiry
                ON cost_budget_reservations(principal_key, expires_at)
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

    def __init__(
        self,
        ledger: CostLedger,
        *,
        daily_token_limit: int = 0,
        monthly_token_limit: int = 0,
        daily_cost_limit_usd: float = 0.0,
        monthly_cost_limit_usd: float = 0.0,
    ) -> None:
        self.ledger = ledger
        self.daily_token_limit = max(0, daily_token_limit)
        self.monthly_token_limit = max(0, monthly_token_limit)
        self.daily_cost_limit_usd = max(0.0, daily_cost_limit_usd)
        self.monthly_cost_limit_usd = max(0.0, monthly_cost_limit_usd)

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

    def admit(
        self,
        *,
        principal_id: str,
        reservation_key: str,
        reserved_tokens: int,
        reserved_cost_usd: float,
        now: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> bool:
        if reserved_tokens < 0 or reserved_cost_usd < 0:
            raise ValueError("Budget reservation values cannot be negative.")

        if (
            self.daily_token_limit <= 0
            and self.monthly_token_limit <= 0
            and self.daily_cost_limit_usd <= 0
            and self.monthly_cost_limit_usd <= 0
        ):
            return True

        timestamp = now or datetime.now(timezone.utc)
        expiry = expires_at or timestamp + timedelta(minutes=5)
        if expiry <= timestamp:
            raise ValueError("Budget reservation must expire in the future.")

        return self.ledger.reserve_budget(
            principal_id=principal_id,
            reservation_key=reservation_key,
            reserved_tokens=reserved_tokens,
            reserved_cost_usd=reserved_cost_usd,
            daily_token_limit=self.daily_token_limit,
            monthly_token_limit=self.monthly_token_limit,
            daily_cost_limit_usd=self.daily_cost_limit_usd,
            monthly_cost_limit_usd=self.monthly_cost_limit_usd,
            now=timestamp,
            expires_at=expiry,
        )

    def release(self, reservation_key: str) -> None:
        self.ledger.release_budget(reservation_key)

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
            "budget": self._budget_status(daily, monthly),
        }

    def _budget_status(
        self,
        daily: CostTotals,
        monthly: CostTotals,
    ) -> dict[str, Any]:
        daily_tokens_ok = (
            self.daily_token_limit <= 0
            or daily.total_tokens <= self.daily_token_limit
        )
        monthly_tokens_ok = (
            self.monthly_token_limit <= 0
            or monthly.total_tokens <= self.monthly_token_limit
        )
        daily_cost_ok = (
            self.daily_cost_limit_usd <= 0
            or daily.estimated_cost_usd <= self.daily_cost_limit_usd
        )
        monthly_cost_ok = (
            self.monthly_cost_limit_usd <= 0
            or monthly.estimated_cost_usd <= self.monthly_cost_limit_usd
        )
        return {
            "within_budget": (
                daily_tokens_ok
                and monthly_tokens_ok
                and daily_cost_ok
                and monthly_cost_ok
            ),
            "daily": {
                "token_limit": self.daily_token_limit,
                "cost_limit_usd": self.daily_cost_limit_usd,
            },
            "monthly": {
                "token_limit": self.monthly_token_limit,
                "cost_limit_usd": self.monthly_cost_limit_usd,
            },
        }

    def report(self, principal_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        daily = self.ledger.totals(
            principal_id,
            since=self._period_start("day", now),
        )
        monthly = self.ledger.totals(
            principal_id,
            since=self._period_start("month", now),
        )
        return {
            "principal_scoped": True,
            "daily": daily.to_dict(),
            "monthly": monthly.to_dict(),
            "budget": self._budget_status(daily, monthly),
        }
