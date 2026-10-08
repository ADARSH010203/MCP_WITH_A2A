"""Optional Redis event transport for distributed A2A task updates."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

import redis.asyncio as redis


class EventBus(Protocol):
    async def ping(self) -> bool: ...
    async def publish(self, task_id: str, event: dict[str, Any]) -> None: ...
    def subscribe(self, task_id: str) -> AsyncIterator[dict[str, Any]]: ...
    async def close(self) -> None: ...


class RedisEventBus:
    """Redis Pub/Sub transport for live task events."""

    def __init__(
        self,
        url: str,
        *,
        channel_prefix: str = "a2a:task:",
        max_message_bytes: int = 1_000_000,
    ) -> None:
        if not url.strip():
            raise ValueError("A2A_EVENT_BUS_URL is required for Redis event bus.")
        if max_message_bytes < 1024:
            raise ValueError("max_message_bytes must be at least 1024")

        self.channel_prefix = channel_prefix
        self.max_message_bytes = max_message_bytes
        self.client = redis.from_url(
            url,
            decode_responses=True,
        )

    def _channel(self, task_id: str) -> str:
        return f"{self.channel_prefix}{task_id}"

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except redis.RedisError:
            return False

    async def publish(self, task_id: str, event: dict[str, Any]) -> None:
        payload = json.dumps(
            event,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        if len(payload.encode("utf-8")) > self.max_message_bytes:
            raise ValueError("A2A event exceeds the configured Redis message limit.")
        await self.client.publish(self._channel(task_id), payload)

    async def subscribe(
        self,
        task_id: str,
    ) -> AsyncIterator[dict[str, Any]]:
        pubsub = self.client.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(self._channel(task_id))
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                raw = message.get("data")
                try:
                    payload = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if isinstance(payload, dict):
                    yield payload
        finally:
            try:
                await pubsub.unsubscribe(self._channel(task_id))
            finally:
                await pubsub.close()

    async def close(self) -> None:
        await self.client.aclose()


def build_event_bus() -> EventBus | None:
    """Build the configured event transport."""
    from app.config.settings import settings

    backend = settings.a2a_event_bus_backend
    if backend in {"", "memory", "local"}:
        return None
    if backend == "redis":
        return RedisEventBus(
            settings.a2a_event_bus_url,
            channel_prefix=settings.a2a_event_bus_channel_prefix,
            max_message_bytes=settings.a2a_event_bus_max_message_bytes,
        )
    raise ValueError(
        "A2A_EVENT_BUS_BACKEND must be 'memory' or 'redis'."
    )
