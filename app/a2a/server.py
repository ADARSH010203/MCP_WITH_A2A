"""FastAPI implementation of the A2A JSON-RPC endpoint."""

import json
import logging
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.config.settings import settings
from sse_starlette.sse import EventSourceResponse

from app.a2a.base_task_manager import TaskManager
from app.a2a.models import (
    A2ARequest,
    AgentCard,
    CancelTaskRequest,
    GetTaskPushNotificationRequest,
    GetTaskRequest,
    InternalError,
    InvalidRequestError,
    RateLimitError,
    JSONParseError,
    JSONRPCResponse,
    SendTaskRequest,
    SendTaskStreamingRequest,
    SetTaskPushNotificationRequest,
    TaskResubscriptionRequest,
)


class A2AServer:
    """Expose A2A task operations over FastAPI and Server-Sent Events."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5000,
        endpoint: str = "/",
        agent_card: AgentCard | None = None,
        task_manager: TaskManager | None = None,
    ) -> None:
        if not endpoint.startswith("/"):
            raise ValueError("endpoint must start with '/'")

        self.host = host
        self.port = port
        self.endpoint = endpoint
        self.agent_card = agent_card
        self.task_manager = task_manager
        self._rate_limit_lock = __import__("asyncio").Lock()
        self._request_timestamps: dict[str, deque[float]] = defaultdict(deque)

        self.app = FastAPI(
            title="A2A Server",
            description="A2A Protocol JSON-RPC API",
            version="1.0.0",
        )
        self.app.add_api_route(
            self.endpoint,
            self._process_request,
            methods=["POST"],
            response_model=None,
        )
        self.app.add_api_route(
            "/.well-known/agent.json",
            self._get_agent_card,
            methods=["GET"],
            response_model=None,
        )

    def start(self) -> None:
        """Start the ASGI application with Uvicorn."""
        if self.agent_card is None:
            raise ValueError("agent_card is required")
        if self.task_manager is None:
            raise ValueError("task_manager is required")

        import uvicorn

        uvicorn.run(self.app, host=self.host, port=self.port)

    async def _get_agent_card(self, _request: Request) -> JSONResponse:
        if self.agent_card is None:
            raise RuntimeError("Agent card is not configured")
        return JSONResponse(self.agent_card.model_dump(exclude_none=True))

    async def _is_rate_limited(self, request: Request) -> bool:
        limit = settings.a2a_rate_limit_per_minute
        if limit <= 0:
            return False

        client_host = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - 60

        async with self._rate_limit_lock:
            timestamps = self._request_timestamps[client_host]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= limit:
                return True

            timestamps.append(now)
            return False

    async def _process_request(
        self, request: Request
    ) -> JSONResponse | EventSourceResponse:
        try:
            if await self._is_rate_limited(request):
                return JSONResponse(
                    JSONRPCResponse(
                        id=None,
                        error=RateLimitError(),
                    ).model_dump(exclude_none=True),
                    status_code=429,
                    headers={"Retry-After": "60"},
                )

            if settings.a2a_api_key:
            if settings.a2a_api_key:
                authorization = request.headers.get("Authorization", "")
                expected = f"Bearer {settings.a2a_api_key}"
                if authorization != expected:
                    return JSONResponse(
                        JSONRPCResponse(
                            id=None,
                            error=InvalidRequestError(message="Authentication required"),
                        ).model_dump(exclude_none=True),
                        status_code=401,
                    )
            body = await request.json()
            rpc_request = A2ARequest.validate_python(body)

            if self.task_manager is None:
                raise RuntimeError("Task manager is not configured")

            handlers = {
                SendTaskRequest: self.task_manager.on_send_task,
                SendTaskStreamingRequest: self.task_manager.on_send_task_subscribe,
                GetTaskRequest: self.task_manager.on_get_task,
                CancelTaskRequest: self.task_manager.on_cancel_task,
                SetTaskPushNotificationRequest: self.task_manager.on_set_task_push_notification,
                GetTaskPushNotificationRequest: self.task_manager.on_get_task_push_notification,
                TaskResubscriptionRequest: self.task_manager.on_resubscribe_to_task,
            }
            handler = next(
                (method for request_type, method in handlers.items() if isinstance(rpc_request, request_type)),
                None,
            )
            if handler is None:
                raise ValueError(f"Unsupported request type: {type(rpc_request).__name__}")

            return self._create_response(await handler(rpc_request))
        except Exception as exc:
            return self._handle_exception(exc)

    def _handle_exception(self, exc: Exception) -> JSONResponse:
        if isinstance(exc, json.JSONDecodeError):
            error = JSONParseError()
        elif isinstance(exc, ValidationError):
            error = InvalidRequestError(data=exc.errors())
        else:
            logging.getLogger(__name__).exception("Unhandled A2A request error")
            error = InternalError()

        return JSONResponse(
            JSONRPCResponse(id=None, error=error).model_dump(exclude_none=True),
            status_code=400,
        )

    @staticmethod
    def _create_response(result: Any) -> JSONResponse | EventSourceResponse:
        if isinstance(result, AsyncIterable):

            async def event_generator() -> AsyncIterable[dict[str, str]]:
                async for item in result:
                    data = item.model_dump_json(exclude_none=True)
                    yield {"data": data}

            return EventSourceResponse(event_generator())

        if isinstance(result, JSONRPCResponse):
            return JSONResponse(result.model_dump(exclude_none=True))

        raise ValueError(f"Unexpected result type: {type(result).__name__}")
