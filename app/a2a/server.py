"""FastAPI implementation of the A2A JSON-RPC endpoint."""

import asyncio
import json
import logging
import secrets
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterable
from typing import Any

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
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
    JSONParseError,
    JSONRPCResponse,
    RateLimitError,
    SendTaskRequest,
    SendTaskStreamingRequest,
    SetTaskPushNotificationRequest,
    TaskResubscriptionRequest,
)
from app.config.settings import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add conservative headers for the JSON-RPC and SSE surface."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


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

        self._rate_limit_lock = asyncio.Lock()
        self._request_timestamps: dict[str, deque[float]] = defaultdict(deque)

        self.app = FastAPI(
            title="A2A Server",
            description="A2A Protocol JSON-RPC API",
            version="1.0.0",
        )
        self.app.add_middleware(SecurityHeadersMiddleware)
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
        self.app.add_api_route(
            "/healthz",
            self._health_check,
            methods=["GET"],
            response_model=None,
        )
        self.app.add_api_route(
            "/readyz",
            self._readiness_check,
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

    async def _health_check(self, _request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def _readiness_check(self, _request: Request) -> JSONResponse:
        ready = self.task_manager is not None and self.agent_card is not None
        return JSONResponse(
            {"status": "ready" if ready else "not_ready"},
            status_code=200 if ready else 503,
        )

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

            if not timestamps:
                self._request_timestamps.pop(client_host, None)
                timestamps = deque()

            if len(self._request_timestamps) > 10000:
                for host, host_timestamps in list(self._request_timestamps.items()):
                    while host_timestamps and host_timestamps[0] <= cutoff:
                        host_timestamps.popleft()
                    if not host_timestamps:
                        self._request_timestamps.pop(host, None)

            if len(timestamps) >= limit:
                return True

            timestamps.append(now)
            return False

    async def _process_request(
        self, request: Request
    ) -> JSONResponse | EventSourceResponse:
        try:
            if settings.a2a_api_key:
                authorization = request.headers.get("Authorization", "")
                presented = (
                    authorization[len("Bearer ") :]
                    if authorization.startswith("Bearer ")
                    else ""
                )
                if not secrets.compare_digest(presented, settings.a2a_api_key):
                    return JSONResponse(
                        JSONRPCResponse(
                            id=None,
                            error=InvalidRequestError(message="Authentication required"),
                        ).model_dump(exclude_none=True),
                        status_code=401,
                    )

            if await self._is_rate_limited(request):
                return JSONResponse(
                    JSONRPCResponse(
                        id=None,
                        error=RateLimitError(),
                    ).model_dump(exclude_none=True),
                    status_code=429,
                    headers={"Retry-After": "60"},
                )

            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > settings.a2a_max_request_body_bytes:
                        return JSONResponse(
                            JSONRPCResponse(
                                id=None,
                                error=InvalidRequestError(
                                    message="Request body exceeds the configured size limit"
                                ),
                            ).model_dump(exclude_none=True),
                            status_code=413,
                        )
                except ValueError:
                    return JSONResponse(
                        JSONRPCResponse(
                            id=None,
                            error=InvalidRequestError(message="Invalid Content-Length header"),
                        ).model_dump(exclude_none=True),
                        status_code=400,
                    )

            body_bytes = await request.body()
            if len(body_bytes) > settings.a2a_max_request_body_bytes:
                return JSONResponse(
                    JSONRPCResponse(
                        id=None,
                        error=InvalidRequestError(
                            message="Request body exceeds the configured size limit"
                        ),
                    ).model_dump(exclude_none=True),
                    status_code=413,
                )

            try:
                body = json.loads(body_bytes)
            except json.JSONDecodeError:
                raise

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
                (
                    method
                    for request_type, method in handlers.items()
                    if isinstance(rpc_request, request_type)
                ),
                None,
            )
            if handler is None:
                raise ValueError(
                    f"Unsupported request type: {type(rpc_request).__name__}"
                )

            return self._create_response(await handler(rpc_request))
        except Exception as exc:
            return self._handle_exception(exc)

    def _handle_exception(self, exc: Exception) -> JSONResponse:
        if isinstance(exc, json.JSONDecodeError):
            error = JSONParseError()
            status_code = 400
        elif isinstance(exc, ValidationError):
            error = InvalidRequestError(data=exc.errors())
            status_code = 400
        else:
            logging.getLogger(__name__).exception("Unhandled A2A request error")
            error = InternalError()
            status_code = 500

        return JSONResponse(
            JSONRPCResponse(id=None, error=error).model_dump(exclude_none=True),
            status_code=status_code,
        )

    @staticmethod
    def _create_response(result: Any) -> JSONResponse | EventSourceResponse:
        if isinstance(result, AsyncIterable):

            async def event_generator() -> AsyncIterable[dict[str, str]]:
                async for item in result:
                    data = item.model_dump_json(exclude_none=True)
                    yield {"data": data}

            return EventSourceResponse(event_generator(), ping=15)

        if isinstance(result, JSONRPCResponse):
            return JSONResponse(result.model_dump(exclude_none=True))

        raise ValueError(f"Unexpected result type: {type(result).__name__}")
