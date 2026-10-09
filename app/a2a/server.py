"""FastAPI implementation of the A2A JSON-RPC endpoint."""

import asyncio
import hashlib
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
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from app.a2a.base_task_manager import TaskManager
from app.a2a.readiness import ReadinessChecker
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
from app.memory.context import use_memory_principal
from app.observability.cost_ledger import CostGovernance, CostLedgerError, build_cost_ledger
from app.observability.context import normalize_request_id, use_request_id
from app.observability.metrics import METRICS
from app.observability.otel import initialize_telemetry, span


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Correlate requests and record bounded operational metrics."""

    async def dispatch(self, request: Request, call_next):
        request_id = normalize_request_id(request.headers.get("X-Request-ID"))
        started = time.perf_counter()

        with use_request_id(request_id):
            try:
                with span(
                    "a2a.http.request",
                    attributes={
                        "http.method": request.method,
                        "http.route": request.url.path,
                    },
                ) as http_span:
                    response = await call_next(request)
                    http_span.set_attribute(
                        "http.status_code",
                        response.status_code,
                    )
                    span_context = http_span.get_span_context()
            except Exception:
                duration_ms = (time.perf_counter() - started) * 1000
                METRICS.increment(
                    "http_requests_total",
                    labels={"method": request.method, "status": "500"},
                )
                METRICS.increment("http_requests_failed_total")
                METRICS.observe("http_request_duration_ms", duration_ms)
                logging.getLogger(__name__).exception(
                    "a2a_request_failed",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": round(duration_ms, 2),
                    },
                )
                raise

        duration_ms = (time.perf_counter() - started) * 1000
        status = str(response.status_code)
        METRICS.increment(
            "http_requests_total",
            labels={"method": request.method, "status": status},
        )
        METRICS.observe("http_request_duration_ms", duration_ms)
        if response.status_code >= 500:
            METRICS.increment("http_requests_failed_total")

        response.headers["X-Request-ID"] = request_id
        if span_context.is_valid:
            response.headers["X-Trace-ID"] = format(span_context.trace_id, "032x")
            response.headers["X-Span-ID"] = format(span_context.span_id, "016x")
        logging.getLogger(__name__).info(
            "a2a_request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response


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
        self.app.add_event_handler("startup", self._startup)
        self.app.add_event_handler("shutdown", self._shutdown)
        self.app.add_middleware(ObservabilityMiddleware)
        self.app.add_middleware(SecurityHeadersMiddleware)
        if getattr(settings, "a2a_cors_origins", ()):
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=list(settings.a2a_cors_origins),
                allow_credentials=False,
                allow_methods=["POST", "GET", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type"],
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
        self.app.add_api_route(
            "/metrics",
            self._metrics_endpoint,
            methods=["GET"],
            response_model=None,
        )
        self.app.add_api_route(
            "/costs",
            self._costs_endpoint,
            methods=["GET"],
            response_model=None,
        )

    async def _startup(self) -> None:
        initialize_telemetry()
        start_event_bus = getattr(
            self.task_manager,
            "start_event_bus",
            None,
        )
        if start_event_bus is not None:
            await start_event_bus()

        start_recovery = getattr(
            self.task_manager,
            "start_recovery_worker",
            None,
        )
        if start_recovery is not None:
            await start_recovery()

    async def _shutdown(self) -> None:
        stop_recovery = getattr(
            self.task_manager,
            "stop_recovery_worker",
            None,
        )
        if stop_recovery is not None:
            await stop_recovery()

        stop_event_bus = getattr(
            self.task_manager,
            "stop_event_bus",
            None,
        )
        if stop_event_bus is not None:
            await stop_event_bus()

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

    async def _costs_endpoint(self, request: Request) -> JSONResponse:
        if not getattr(settings, "a2a_cost_ledger_enabled", False):
            return JSONResponse(
                {"status": "disabled"},
                status_code=404,
            )

        configured_api_key = getattr(settings, "a2a_api_key", "")
        if not configured_api_key:
            return JSONResponse(
                {
                    "status": "unavailable",
                    "detail": "Cost reporting requires A2A_API_KEY.",
                },
                status_code=503,
            )

        authorization = request.headers.get("Authorization", "")
        scheme, _, credentials = authorization.partition(" ")
        presented = (
            credentials.strip()
            if scheme.casefold() == "bearer"
            else ""
        )
        if not secrets.compare_digest(presented, configured_api_key):
            return JSONResponse(
                JSONRPCResponse(
                    id=None,
                    error=InvalidRequestError(
                        message="Authentication required"
                    ),
                ).model_dump(exclude_none=True),
                status_code=401,
            )

        try:
            governance = CostGovernance(
                build_cost_ledger(),
                daily_token_limit=getattr(
                    settings,
                    "a2a_daily_token_limit_per_principal",
                    0,
                ),
                monthly_token_limit=getattr(
                    settings,
                    "a2a_monthly_token_limit_per_principal",
                    0,
                ),
                daily_cost_limit_usd=getattr(
                    settings,
                    "a2a_daily_cost_limit_usd_per_principal",
                    0.0,
                ),
                monthly_cost_limit_usd=getattr(
                    settings,
                    "a2a_monthly_cost_limit_usd_per_principal",
                    0.0,
                ),
            )
            principal_id = self._principal_id_from_request(request)
            return JSONResponse(governance.report(principal_id))
        except CostLedgerError as exc:
            return JSONResponse(
                {
                    "status": "unavailable",
                    "detail": str(exc),
                },
                status_code=503,
            )

    async def _metrics_endpoint(self, request: Request) -> JSONResponse:
        if not getattr(settings, "prometheus_metrics_enabled", True):
            return JSONResponse(
                {"status": "disabled"},
                status_code=404,
            )

        if settings.a2a_api_key:
            authorization = request.headers.get("Authorization", "")
            scheme, _, credentials = authorization.partition(" ")
            presented = (
                credentials.strip()
                if scheme.casefold() == "bearer"
                else ""
            )
            if not secrets.compare_digest(presented, settings.a2a_api_key):
                return JSONResponse(
                    JSONRPCResponse(
                        id=None,
                        error=InvalidRequestError(
                            message="Authentication required"
                        ),
                    ).model_dump(exclude_none=True),
                    status_code=401,
                )

        if "text/plain" in request.headers.get("accept", ""):
            from fastapi.responses import PlainTextResponse

            return PlainTextResponse(
                METRICS.prometheus(),
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )
        return JSONResponse(METRICS.snapshot())

    async def _readiness_check(self, _request: Request) -> JSONResponse:
        ready, checks = ReadinessChecker(
            task_manager=self.task_manager,
            agent_card=self.agent_card,
        ).run()

        return JSONResponse(
            {
                "status": "ready" if ready else "not_ready",
                "checks": checks,
            },
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

    async def _read_request_body(self, request: Request) -> bytes | JSONResponse:
        """Read the request body without buffering beyond the configured limit."""
        limit = settings.a2a_max_request_body_bytes
        content_length = request.headers.get("content-length")

        if content_length is not None:
            try:
                if int(content_length) > limit:
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

        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > limit:
                return JSONResponse(
                    JSONRPCResponse(
                        id=None,
                        error=InvalidRequestError(
                            message="Request body exceeds the configured size limit"
                        ),
                    ).model_dump(exclude_none=True),
                    status_code=413,
                )
            body.extend(chunk)

        return bytes(body)

    async def _process_request(
        self, request: Request
    ) -> JSONResponse | EventSourceResponse:
        try:
            principal_id = self._principal_id_from_request(request)
            if principal_id is None:
                return JSONResponse(
                    JSONRPCResponse(
                        id=None,
                        error=InvalidRequestError(
                            message="Authentication required"
                        ),
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

            content_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
            if content_type != "application/json":
                return JSONResponse(
                    JSONRPCResponse(
                        id=None,
                        error=InvalidRequestError(
                            message="Content-Type must be application/json"
                        ),
                    ).model_dump(exclude_none=True),
                    status_code=415,
                )

            body_bytes = await self._read_request_body(request)
            if isinstance(body_bytes, JSONResponse):
                return body_bytes

            body = json.loads(body_bytes)

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

            with use_memory_principal(principal_id):
                return self._create_response(await handler(rpc_request))
        except Exception as exc:
            return self._handle_exception(exc)

    @staticmethod
    def _authentication_configured() -> bool:
        return bool(getattr(settings, "a2a_api_key", "")) or bool(
            getattr(settings, "a2a_principal_api_keys", {})
        )

    @staticmethod
    def _principal_id_from_request(request: Request) -> str | None:
        """Authenticate the bearer credential and derive its stable principal."""
        authorization = request.headers.get("Authorization", "")
        scheme, _, credentials = authorization.partition(" ")
        presented = credentials.strip() if scheme.casefold() == "bearer" else ""

        principal_keys = getattr(settings, "a2a_principal_api_keys", {}) or {}
        matched_principal: str | None = None
        for principal_id, api_key in sorted(principal_keys.items()):
            if secrets.compare_digest(presented, api_key):
                matched_principal = principal_id

        if matched_principal is not None:
            return "client:" + matched_principal

        configured_api_key = getattr(settings, "a2a_api_key", "")
        if configured_api_key:
            if secrets.compare_digest(presented, configured_api_key):
                return "bearer:" + hashlib.sha256(
                    presented.encode("utf-8")
                ).hexdigest()
            return None

        if principal_keys:
            return None

        # Unauthenticated local/demo deployments share one anonymous budget
        # principal rather than allowing arbitrary bearer strings to mint IDs.
        return "anonymous"

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
