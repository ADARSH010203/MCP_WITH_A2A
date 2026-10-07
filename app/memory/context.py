"""Request-scoped trusted principal identity for persistent memory."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_MEMORY_PRINCIPAL: ContextVar[str] = ContextVar(
    "memory_principal_id",
    default="default",
)


def get_memory_principal_id() -> str:
    """Return the trusted principal associated with the current request."""
    return _MEMORY_PRINCIPAL.get()


@contextmanager
def use_memory_principal(principal_id: str) -> Iterator[None]:
    """Temporarily bind a trusted principal to the current execution context."""
    if not isinstance(principal_id, str) or not principal_id.strip():
        raise ValueError("principal_id must be a non-empty string")
    if len(principal_id) > 256:
        raise ValueError("principal_id is too long")

    token = _MEMORY_PRINCIPAL.set(principal_id)
    try:
        yield
    finally:
        _MEMORY_PRINCIPAL.reset(token)
