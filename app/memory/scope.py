"""Opaque memory-scope identifiers for tenant/session/agent isolation."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass


class MemoryScopeError(ValueError):
    """Raised when a memory scope contains an invalid identity component."""


@dataclass(frozen=True)
class MemoryScope:
    """Trusted principal, session, and agent identity for persistent memory."""

    principal_id: str
    session_id: str
    agent_type: str

    def __post_init__(self) -> None:
        for name, value in (
            ("principal_id", self.principal_id),
            ("session_id", self.session_id),
            ("agent_type", self.agent_type),
        ):
            if not isinstance(value, str) or not value.strip():
                raise MemoryScopeError(f"{name} must be a non-empty string")
            if len(value) > 256:
                raise MemoryScopeError(f"{name} is too long")

    def session_key(self, secret: str) -> str:
        """Return an opaque deterministic key for the principal/session scope."""
        if not secret:
            raise MemoryScopeError(
                "A memory namespace secret is required for persistent memory."
            )

        canonical = "\\x1f".join(
            (self.principal_id, self.session_id)
        ).encode("utf-8")
        return hmac.new(
            secret.encode("utf-8"),
            canonical,
            hashlib.sha256,
        ).hexdigest()

    def key(self, secret: str) -> str:
        """Return an opaque deterministic scope key."""
        if not secret:
            raise MemoryScopeError(
                "A memory namespace secret is required for persistent memory."
            )

        canonical = "\x1f".join(
            (self.principal_id, self.session_id, self.agent_type)
        ).encode("utf-8")
        return hmac.new(
            secret.encode("utf-8"),
            canonical,
            hashlib.sha256,
        ).hexdigest()
