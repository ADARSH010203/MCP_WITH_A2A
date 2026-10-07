"""Comprehensive dependency and configuration readiness checks."""

from __future__ import annotations

import os
import socket
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.config.settings import settings


@dataclass(frozen=True)
class ReadinessCheck:
    """One named readiness result."""

    name: str
    ready: bool
    detail: str


class ReadinessChecker:
    """Evaluate startup-critical dependencies without exposing secrets."""

    def __init__(self, task_manager=None, agent_card=None) -> None:
        self.task_manager = task_manager
        self.agent_card = agent_card

    def run(self) -> tuple[bool, dict[str, dict[str, str]]]:
        checks = [
            self._task_manager_check(),
            self._agent_card_check(),
            self._groq_check(),
            self._memory_check(),
            self._task_store_check(),
            self._mcp_config_check(),
            self._remote_specialist_config_check(),
        ]
        return (
            all(check.ready for check in checks),
            {
                check.name: {
                    "status": "ok" if check.ready else "failed",
                    "detail": check.detail,
                }
                for check in checks
            },
        )

    def _task_manager_check(self) -> ReadinessCheck:
        if self.task_manager is None:
            return ReadinessCheck("task_manager", False, "Task manager is not configured.")

        return ReadinessCheck("task_manager", True, "Configured.")

    def _agent_card_check(self) -> ReadinessCheck:
        if self.agent_card is None:
            return ReadinessCheck("agent_card", False, "Agent Card is not configured.")

        if not self.agent_card.skills:
            return ReadinessCheck("agent_card", False, "Agent Card advertises no skills.")

        return ReadinessCheck("agent_card", True, "Configured with advertised skills.")

    def _groq_check(self) -> ReadinessCheck:
        if not settings.groq_api_key:
            return ReadinessCheck(
                "groq",
                False,
                "GROQ_API_KEY is not configured.",
            )
        return ReadinessCheck("groq", True, "API credential is configured.")

    def _memory_check(self) -> ReadinessCheck:
        if not settings.a2a_memory_namespace_secret:
            return ReadinessCheck(
                "memory",
                False,
                "A2A_MEMORY_NAMESPACE_SECRET is not configured.",
            )

        path = settings.a2a_memory_db_path
        if path == ":memory:":
            return ReadinessCheck("memory", True, "In-memory store configured.")

        target = Path(path)
        parent = target.parent
        if not parent.exists() or not os.access(parent, os.W_OK):
            return ReadinessCheck(
                "memory",
                False,
                "Memory database directory is not writable.",
            )

        if target.exists():
            try:
                connection = sqlite3.connect(
                    path,
                    timeout=2,
                )
                connection.execute("SELECT 1").fetchone()
                connection.close()
            except sqlite3.Error:
                return ReadinessCheck(
                    "memory",
                    False,
                    "Memory database is not reachable.",
                )

        return ReadinessCheck("memory", True, "Memory store is configured and writable.")

    def _task_store_check(self) -> ReadinessCheck:
        if self.task_manager is None:
            return ReadinessCheck(
                "task_store",
                False,
                "Task manager is not configured.",
            )

        checker = getattr(self.task_manager, "is_ready", None)
        if checker is None:
            return ReadinessCheck(
                "task_store",
                True,
                "Task manager does not expose a readiness probe.",
            )

        try:
            if checker():
                return ReadinessCheck("task_store", True, "Task store responded successfully.")
        except Exception:
            return ReadinessCheck(
                "task_store",
                False,
                "Task store readiness probe raised an error.",
            )

        return ReadinessCheck(
            "task_store",
            False,
            "Task store readiness probe failed.",
        )

    @staticmethod
    def _validate_url(
        value: str,
        *,
        require_https: bool = False,
    ) -> tuple[bool, str]:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False, "URL is invalid."
        if parsed.username or parsed.password:
            return False, "URL must not contain embedded credentials."
        if require_https and parsed.scheme != "https":
            return False, "URL must use HTTPS."
        return True, "URL is valid."

    def _mcp_config_check(self) -> ReadinessCheck:
        valid, detail = self._validate_url(settings.mcp_url)
        if not valid:
            return ReadinessCheck("mcp", False, detail)

        parsed = urlparse(settings.mcp_url)
        connection = None
        try:
            connection = socket.create_connection(
                (
                    parsed.hostname,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                ),
                timeout=1.0,
            )
        except (OSError, ValueError):
            return ReadinessCheck("mcp", False, "MCP service is not reachable.")
        finally:
            if connection is not None:
                connection.close()

        return ReadinessCheck("mcp", True, "MCP endpoint host is reachable.")

    def _remote_specialist_config_check(self) -> ReadinessCheck:
        urls = settings.a2a_specialist_urls
        keys = settings.a2a_specialist_api_keys

        unknown_keys = set(keys) - set(urls)
        if unknown_keys:
            names = ", ".join(sorted(unknown_keys))
            return ReadinessCheck(
                "remote_specialists",
                False,
                f"Credentials configured without URLs: {names}.",
            )

        if not urls:
            return ReadinessCheck(
                "remote_specialists",
                True,
                "No remote specialists configured.",
            )

        for agent, url in urls.items():
            valid, detail = self._validate_url(
                url,
                require_https=settings.a2a_remote_require_https,
            )
            if not valid:
                return ReadinessCheck(
                    "remote_specialists",
                    False,
                    f"{agent}: {detail}",
                )
            if settings.a2a_remote_require_auth and not keys.get(agent):
                return ReadinessCheck(
                    "remote_specialists",
                    False,
                    f"{agent}: API key is required.",
                )

        return ReadinessCheck(
            "remote_specialists",
            True,
            f"{len(urls)} remote specialist configuration(s) validated.",
        )
