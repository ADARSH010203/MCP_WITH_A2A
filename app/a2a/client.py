import json
from collections.abc import AsyncIterable
from typing import Any

import httpx
from httpx_sse import aconnect_sse

from app.config.settings import settings

from app.a2a.models import (
    A2AClientHTTPError,
    A2AClientJSONError,
    AgentCard,
    CancelTaskRequest,
    CancelTaskResponse,
    GetTaskPushNotificationRequest,
    GetTaskPushNotificationResponse,
    GetTaskRequest,
    GetTaskResponse,
    JSONRPCRequest,
    SendTaskRequest,
    SendTaskResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
    SetTaskPushNotificationRequest,
    SetTaskPushNotificationResponse,
)


class A2AClient:
    """Small async client for the A2A JSON-RPC and SSE endpoints."""

    def __init__(
        self,
        agent_card: AgentCard | None = None,
        url: str | None = None,
        api_key: str | None = None,
    ):
        self.api_key = settings.a2a_api_key if api_key is None else api_key
        if agent_card is not None:
            self.url = agent_card.url
        elif url:
            self.url = url.rstrip("/")
        else:
            raise ValueError("Provide either agent_card or url")

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            return {}
        return {"Authorization": f"Bearer {self.api_key}"}

    async def send_task(self, payload: dict[str, Any]) -> SendTaskResponse:
        request = SendTaskRequest(params=payload)
        response = await self._send_request(request)
        return SendTaskResponse.model_validate(response)

    async def send_task_streaming(
        self, payload: dict[str, Any]
    ) -> AsyncIterable[SendTaskStreamingResponse]:
        request = SendTaskStreamingRequest(params=payload)
        timeout = httpx.Timeout(connect=10, read=None, write=10, pool=10)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with aconnect_sse(
                    client,
                    "POST",
                    self.url,
                    json=request.model_dump(exclude_none=True),
                    headers=self._headers(),
                ) as event_source:
                    event_source.response.raise_for_status()

                    async for event in event_source.aiter_sse():
                        if not event.data:
                            continue
                        try:
                            yield SendTaskStreamingResponse.model_validate_json(
                                event.data
                            )
                        except (json.JSONDecodeError, ValueError) as exc:
                            raise A2AClientJSONError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise A2AClientHTTPError(exc.response.status_code, str(exc)) from exc
        except httpx.RequestError as exc:
            raise A2AClientHTTPError(500, str(exc)) from exc

    async def _send_request(self, request: JSONRPCRequest) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.url,
                    json=request.model_dump(exclude_none=True),
                    headers=self._headers(),
                )
                response.raise_for_status()
                try:
                    return response.json()
                except json.JSONDecodeError as exc:
                    raise A2AClientJSONError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise A2AClientHTTPError(exc.response.status_code, str(exc)) from exc
        except httpx.RequestError as exc:
            raise A2AClientHTTPError(500, str(exc)) from exc

    async def get_task(self, payload: dict[str, Any]) -> GetTaskResponse:
        request = GetTaskRequest(params=payload)
        return GetTaskResponse.model_validate(await self._send_request(request))

    async def cancel_task(self, payload: dict[str, Any]) -> CancelTaskResponse:
        request = CancelTaskRequest(params=payload)
        return CancelTaskResponse.model_validate(await self._send_request(request))

    async def set_task_callback(
        self, payload: dict[str, Any]
    ) -> SetTaskPushNotificationResponse:
        request = SetTaskPushNotificationRequest(params=payload)
        return SetTaskPushNotificationResponse.model_validate(
            await self._send_request(request)
        )

    async def get_task_callback(
        self, payload: dict[str, Any]
    ) -> GetTaskPushNotificationResponse:
        request = GetTaskPushNotificationRequest(params=payload)
        return GetTaskPushNotificationResponse.model_validate(
            await self._send_request(request)
        )
