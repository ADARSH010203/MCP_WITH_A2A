"""Remote specialist adapter that speaks A2A to an independent agent service."""

import asyncio
from collections.abc import AsyncIterable
from typing import Any
from uuid import uuid4

from app.a2a.card_resolver import A2ACardResolver
from app.a2a.client import A2AClient
from app.a2a.models import AgentCard, TaskState


class RemoteA2ASpecialist:
    """Expose a remote A2A specialist through the local Agent interface."""

    def __init__(
        self,
        agent_type: str,
        url: str,
        api_key: str = "",
    ) -> None:
        self.agent_type = agent_type
        self.url = url.rstrip("/")
        self.api_key = api_key
        self._agent_card: AgentCard | None = None
        self._client: A2AClient | None = None

    @property
    def agent_card(self) -> AgentCard | None:
        return self._agent_card

    def _ensure_client(self) -> A2AClient:
        if self._client is not None:
            return self._client

        resolver = A2ACardResolver(
            self.url,
            api_key=self.api_key,
        )
        card = resolver.get_agent_card()
        if not card.skills:
            raise ValueError(
                f"Remote agent '{self.agent_type}' returned an Agent Card without skills."
            )

        self._agent_card = card
        self._client = A2AClient(
            agent_card=card,
            api_key=self.api_key,
        )
        return self._client

    @staticmethod
    def _text_from_parts(parts: list[Any] | None) -> list[str]:
        texts: list[str] = []
        for part in parts or []:
            if isinstance(part, dict) and part.get("type") == "text":
                value = str(part.get("text", "")).strip()
                if value:
                    texts.append(value)
        return texts

    @classmethod
    def _task_content(cls, task: Any) -> str:
        artifacts = getattr(task, "artifacts", None) or []
        content: list[str] = []

        for artifact in artifacts:
            content.extend(
                cls._text_from_parts(
                    [
                        part.model_dump() if hasattr(part, "model_dump") else part
                        for part in (getattr(artifact, "parts", None) or [])
                    ]
                )
            )

        if content:
            return "\n\n".join(content)

        status_message = getattr(getattr(task, "status", None), "message", None)
        if status_message is not None:
            parts = [
                part.model_dump() if hasattr(part, "model_dump") else part
                for part in (getattr(status_message, "parts", None) or [])
            ]
            content = cls._text_from_parts(parts)
            if content:
                return "\n\n".join(content)

        return ""

    def _payload(
        self,
        task_id: str,
        session_id: str,
        query: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": task_id,
            "sessionId": session_id,
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": query}],
            },
            "metadata": {
                "source": "multi-agent-coordinator",
                "specialist": self.agent_type,
                **(metadata or {}),
            },
        }

    def invoke(self, query: str, session_id: str) -> dict[str, Any]:
        task_id = uuid4().hex

        async def call() -> dict[str, Any]:
            client = self._ensure_client()
            response = await client.send_task(
                self._payload(task_id, session_id, query)
            )
            if response.error is not None:
                return {
                    "agent": self.agent_type,
                    "status": "error",
                    "content": f"Remote A2A error: {response.error.message}",
                    "execution_mode": "remote-a2a",
                    "remote_url": self.url,
                    "remote_task_id": task_id,
                }

            task = response.result
            if task is None:
                return {
                    "agent": self.agent_type,
                    "status": "error",
                    "content": "Remote A2A service returned no task.",
                    "execution_mode": "remote-a2a",
                    "remote_url": self.url,
                    "remote_task_id": task_id,
                }

            state = task.status.state
            content = self._task_content(task)
            result = {
                "agent": self.agent_type,
                "status": (
                    "completed"
                    if state == TaskState.COMPLETED
                    else (
                        "input_required"
                        if state == TaskState.INPUT_REQUIRED
                        else "error"
                    )
                ),
                "content": content or f"Remote task ended with state={state.value}.",
                "execution_mode": "remote-a2a",
                "remote_url": self.url,
                "remote_task_id": task_id,
                "remote_agent_card": (
                    self._agent_card.model_dump(exclude_none=True)
                    if self._agent_card is not None
                    else {}
                ),
            }
            if state == TaskState.INPUT_REQUIRED:
                result["require_user_input"] = True
            return result

        try:
            return asyncio.run(call())
        except Exception as exc:
            return {
                "agent": self.agent_type,
                "status": "error",
                "content": f"Remote A2A call failed: {exc}",
                "execution_mode": "remote-a2a",
                "remote_url": self.url,
                "remote_task_id": task_id,
            }

    async def stream(
        self,
        query: str,
        session_id: str,
    ) -> AsyncIterable[dict[str, Any]]:
        task_id = uuid4().hex
        client = self._ensure_client()

        try:
            async for event in client.send_task_streaming(
                self._payload(task_id, session_id, query)
            ):
                if event.error is not None:
                    yield {
                        "agent": self.agent_type,
                        "status": "error",
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": f"Remote A2A error: {event.error.message}",
                        "execution_mode": "remote-a2a",
                        "remote_url": self.url,
                        "remote_task_id": task_id,
                    }
                    return

                result = event.result
                if result is None:
                    continue

                metadata = getattr(result, "metadata", None) or {}
                if hasattr(result, "artifact"):
                    content = self._text_from_parts(
                        [
                            part.model_dump()
                            if hasattr(part, "model_dump")
                            else part
                            for part in (result.artifact.parts or [])
                        ]
                    )
                    yield {
                        "agent": self.agent_type,
                        "status": "completed",
                        "is_task_complete": True,
                        "require_user_input": False,
                        "content": "\n\n".join(content),
                        "execution_mode": "remote-a2a",
                        "remote_url": self.url,
                        "remote_task_id": task_id,
                        "remote_metadata": metadata,
                    }
                    continue

                state = result.status.state
                yield {
                    "agent": self.agent_type,
                    "status": (
                        "input_required"
                        if state == TaskState.INPUT_REQUIRED
                        else (
                            "completed"
                            if state == TaskState.COMPLETED
                            else (
                                "timeout"
                                if state == TaskState.FAILED
                                else "working"
                            )
                        )
                    ),
                    "is_task_complete": state
                    in {TaskState.COMPLETED, TaskState.INPUT_REQUIRED, TaskState.FAILED},
                    "require_user_input": state == TaskState.INPUT_REQUIRED,
                    "content": self._text_from_parts(
                        [
                            part.model_dump()
                            if hasattr(part, "model_dump")
                            else part
                            for part in (
                                getattr(result.status.message, "parts", None) or []
                            )
                        ]
                    )
                    or f"Remote task state: {state.value}.",
                    "execution_mode": "remote-a2a",
                    "remote_url": self.url,
                    "remote_task_id": task_id,
                    "remote_metadata": metadata,
                }
        except Exception as exc:
            yield {
                "agent": self.agent_type,
                "status": "error",
                "is_task_complete": False,
                "require_user_input": False,
                "content": f"Remote A2A streaming failed: {exc}",
                "execution_mode": "remote-a2a",
                "remote_url": self.url,
                "remote_task_id": task_id,
            }
