"""Request-scoped observability context."""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator
from uuid import uuid4


_REQUEST_ID: ContextVar[str] = ContextVar(
    "a2a_request_id",
    default="",
)


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def get_request_id() -> str:
    """Return the current request correlation ID."""
    value = _REQUEST_ID.get()
    return value or "untracked"


def normalize_request_id(value: str | None) -> str:
    """Accept safe caller IDs or generate a new opaque ID."""
    candidate = (value or "").strip()
    if _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex


@contextmanager
def use_request_id(request_id: str) -> Iterator[None]:
    """Bind a validated request correlation ID."""
    normalized = normalize_request_id(request_id)
    token = _REQUEST_ID.set(normalized)
    try:
        yield
    finally:
        _REQUEST_ID.reset(token)
