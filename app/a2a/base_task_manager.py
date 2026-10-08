
import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable

from app.a2a.event_bus import EventBus, build_event_bus
from app.a2a.models import (
    Artifact,
    CancelTaskRequest,
    CancelTaskResponse,
    GetTaskPushNotificationRequest,
    GetTaskPushNotificationResponse,
    GetTaskRequest,
    GetTaskResponse,
    InternalError,
    JSONRPCError,
    JSONRPCResponse,
    PushNotificationConfig,
    SendTaskRequest,
    SendTaskResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
    SetTaskPushNotificationRequest,
    SetTaskPushNotificationResponse,
    Task,
    TaskIdParams,
    TaskNotCancelableError,
    TaskNotFoundError,
    TaskPushNotificationConfig,
    TaskQueryParams,
    TaskResubscriptionRequest,
    TaskSendParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from app.a2a.store_protocol import TaskStore
from app.a2a.task_store_factory import build_task_store
from app.a2a.utils import new_not_implemented_error
from app.config.settings import settings

logger = logging.getLogger(__name__)


class TaskManager(ABC):
    @abstractmethod
    async def on_get_task(self, request: GetTaskRequest) -> GetTaskResponse:
        pass

    @abstractmethod
    async def on_cancel_task(self, request: CancelTaskRequest) -> CancelTaskResponse:
        pass

    @abstractmethod
    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        pass

    @abstractmethod
    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        pass

    @abstractmethod
    async def on_set_task_push_notification(
        self, request: SetTaskPushNotificationRequest
    ) -> SetTaskPushNotificationResponse:
        pass

    @abstractmethod
    async def on_get_task_push_notification(
        self, request: GetTaskPushNotificationRequest
    ) -> GetTaskPushNotificationResponse:
        pass

    @abstractmethod
    async def on_resubscribe_to_task(
        self, request: TaskResubscriptionRequest
    ) -> AsyncIterable[SendTaskResponse] | JSONRPCResponse:
        pass


class InMemoryTaskManager(TaskManager):
    def __init__(self, store: TaskStore | None = None):
        self.store = store or build_task_store()
        self.store.purge_expired(settings.a2a_task_retention_days)
        self.store.purge_expired_leases()
        self.tasks: dict[str, Task] = self.store.load_tasks()
        self.push_notification_infos: dict[str, PushNotificationConfig] = (
            self.store.load_push_notification_configs()
        )
        self.lock = asyncio.Lock()
        self.task_sse_subscribers: dict[str, list[asyncio.Queue]] = {}
        self.subscriber_lock = asyncio.Lock()
        self.event_bus: EventBus | None = build_event_bus()
        self.event_bus_ready = self.event_bus is None
        self.event_bridge_tasks: dict[int, asyncio.Task[None]] = {}

    def is_ready(self) -> bool:
        """Return whether the durable task store is reachable."""
        return self.store.ping()

    async def get_stored_task(self, task_id: str) -> Task | None:
        """Read the latest task state from durable storage."""
        async with self.lock:
            task = self.store.load_task(task_id)
            if task is None:
                self.tasks.pop(task_id, None)
                return None
            self.tasks[task_id] = task
            return task

    async def on_get_task(self, request: GetTaskRequest) -> GetTaskResponse:
        logger.info(f"Getting task {request.params.id}")
        task_query_params: TaskQueryParams = request.params

        async with self.lock:
            task = self.store.load_task(task_query_params.id)
            if task is not None:
                self.tasks[task_query_params.id] = task
            if task is None:
                return GetTaskResponse(id=request.id, error=TaskNotFoundError())

            task_result = self.append_task_history(
                task, task_query_params.historyLength
            )

        return GetTaskResponse(id=request.id, result=task_result)

    async def on_cancel_task(self, request: CancelTaskRequest) -> CancelTaskResponse:
        logger.info(f"Cancelling task {request.params.id}")
        task_id_params: TaskIdParams = request.params

        async with self.lock:
            task = self.tasks.get(task_id_params.id)
            if task is None:
                return CancelTaskResponse(id=request.id, error=TaskNotFoundError())

        return CancelTaskResponse(id=request.id, error=TaskNotCancelableError())

    @abstractmethod
    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        pass

    @abstractmethod
    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        pass

    async def set_push_notification_info(
        self, task_id: str, notification_config: PushNotificationConfig
    ):
        async with self.lock:
            task = self.tasks.get(task_id)
            if task is None:
                raise ValueError(f"Task not found for {task_id}")

            self.push_notification_infos[task_id] = notification_config
            self.store.save_push_notification_config(task_id, notification_config)

        return

    async def get_push_notification_info(self, task_id: str) -> PushNotificationConfig:
        async with self.lock:
            task = self.tasks.get(task_id)
            if task is None:
                raise ValueError(f"Task not found for {task_id}")

            return self.push_notification_infos[task_id]

        return

    async def has_push_notification_info(self, task_id: str) -> bool:
        async with self.lock:
            return task_id in self.push_notification_infos

    async def on_set_task_push_notification(
        self, request: SetTaskPushNotificationRequest
    ) -> SetTaskPushNotificationResponse:
        logger.info(f"Setting task push notification {request.params.id}")
        task_notification_params: TaskPushNotificationConfig = request.params

        try:
            await self.set_push_notification_info(
                task_notification_params.id,
                task_notification_params.pushNotificationConfig,
            )
        except Exception as e:
            logger.error(f"Error while setting push notification info: {e}")
            return JSONRPCResponse(
                id=request.id,
                error=InternalError(
                    message="An error occurred while setting push notification info"
                ),
            )

        return SetTaskPushNotificationResponse(
            id=request.id, result=task_notification_params
        )

    async def on_get_task_push_notification(
        self, request: GetTaskPushNotificationRequest
    ) -> GetTaskPushNotificationResponse:
        logger.info(f"Getting task push notification {request.params.id}")
        task_params: TaskIdParams = request.params

        try:
            notification_info = await self.get_push_notification_info(task_params.id)
        except Exception as e:
            logger.error(f"Error while getting push notification info: {e}")
            return GetTaskPushNotificationResponse(
                id=request.id,
                error=InternalError(
                    message="An error occurred while getting push notification info"
                ),
            )

        return GetTaskPushNotificationResponse(
            id=request.id,
            result=TaskPushNotificationConfig(
                id=task_params.id, pushNotificationConfig=notification_info
            ),
        )

    async def get_or_create_task(
        self, task_send_params: TaskSendParams
    ) -> tuple[Task, bool]:
        """Atomically return an existing task or create a new one.

        Returns ``(task, created)``. Reusing a task ID with a different
        session or message is rejected to protect idempotency.
        """
        logger.info("Getting or creating task %s", task_send_params.id)

        async with self.lock:
            task = self.store.load_task(task_send_params.id)
            if task is not None:
                self.tasks[task_send_params.id] = task
                existing_message = (task.history or [None])[0]
                if (
                    task.sessionId != task_send_params.sessionId
                    or existing_message is None
                    or existing_message.model_dump()
                    != task_send_params.message.model_dump()
                ):
                    raise ValueError(
                        f"Task ID '{task_send_params.id}' is already used by a different request"
                    )
                return task, False

            task = Task(
                id=task_send_params.id,
                sessionId=task_send_params.sessionId,
                status=TaskStatus(state=TaskState.SUBMITTED),
                history=[task_send_params.message],
            )
            task, created = self.store.create_task_if_absent(task)
            self.tasks[task.id] = task
            return task, created

    async def upsert_task(self, task_send_params: TaskSendParams) -> Task:
        """Create a task or return the existing matching task."""
        task, _ = await self.get_or_create_task(task_send_params)
        return task

    async def on_resubscribe_to_task(
        self, request: TaskResubscriptionRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        return new_not_implemented_error(request.id)

    async def update_store(
        self, task_id: str, status: TaskStatus, artifacts: list[Artifact]
    ) -> Task:
        async with self.lock:
            task = self.store.load_task(task_id)
            if task is None:
                logger.error(f"Task {task_id} not found for updating the task")
                raise ValueError(f"Task {task_id} not found")
            self.tasks[task_id] = task
            task.status = status

            if status.message is not None:
                if task.history is None:
                    task.history = []
                task.history.append(status.message)

            if artifacts is not None:
                if task.artifacts is None:
                    task.artifacts = []
                task.artifacts.extend(artifacts)

            self.store.save_task(task)
            return task

    def append_task_history(self, task: Task, historyLength: int | None):
        new_task = task.model_copy()
        history = new_task.history or []
        if historyLength is not None and historyLength > 0:
            new_task.history = history[-historyLength:]
        else:
            new_task.history = []

        return new_task

    async def start_event_bus(self) -> None:
        """Validate the distributed event transport before serving traffic."""
        if self.event_bus is None:
            self.event_bus_ready = True
            return
        self.event_bus_ready = await self.event_bus.ping()
        if not self.event_bus_ready:
            raise RuntimeError("Configured A2A event bus is unavailable.")

    async def stop_event_bus(self) -> None:
        """Close the event transport and subscriber bridge tasks."""
        bridge_tasks = list(self.event_bridge_tasks.values())
        for task in bridge_tasks:
            task.cancel()
        if bridge_tasks:
            await asyncio.gather(*bridge_tasks, return_exceptions=True)
        self.event_bridge_tasks.clear()

        if self.event_bus is not None:
            await self.event_bus.close()
        self.event_bus_ready = False

    @staticmethod
    def _serialize_sse_event(event) -> dict[str, object]:
        event_type = (
            "JSONRPCError"
            if isinstance(event, JSONRPCError)
            else event.__class__.__name__
        )
        return {
            "type": event_type,
            "payload": event.model_dump(mode="json"),
        }

    @staticmethod
    def _deserialize_sse_event(data: dict[str, object]):
        event_type = data.get("type")
        payload = data.get("payload")
        if not isinstance(payload, dict):
            return None

        event_models = {
            "JSONRPCError": JSONRPCError,
            "TaskArtifactUpdateEvent": TaskArtifactUpdateEvent,
            "TaskStatusUpdateEvent": TaskStatusUpdateEvent,
        }
        model = event_models.get(str(event_type))
        if model is None:
            return None
        try:
            return model.model_validate(payload)
        except (TypeError, ValueError):
            return None

    async def _bridge_event_bus(
        self,
        task_id: str,
        sse_event_queue: asyncio.Queue,
    ) -> None:
        if self.event_bus is None:
            return
        try:
            async for data in self.event_bus.subscribe(task_id):
                event = self._deserialize_sse_event(data)
                if event is not None:
                    await sse_event_queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Distributed SSE event bridge failed for task %s",
                task_id,
            )

    async def setup_sse_consumer(self, task_id: str, is_resubscribe: bool = False):
        async with self.subscriber_lock:
            if task_id not in self.task_sse_subscribers:
                if is_resubscribe:
                    raise ValueError("Task not found for resubscription")
                self.task_sse_subscribers[task_id] = []

            sse_event_queue = asyncio.Queue(maxsize=0)
            self.task_sse_subscribers[task_id].append(sse_event_queue)

            if self.event_bus is not None:
                bridge = asyncio.create_task(
                    self._bridge_event_bus(task_id, sse_event_queue),
                    name=f"sse-event-bridge-{task_id}",
                )
                self.event_bridge_tasks[id(sse_event_queue)] = bridge

            return sse_event_queue

    async def enqueue_events_for_sse(self, task_id, task_update_event):
        if self.event_bus is not None:
            try:
                await self.event_bus.publish(
                    task_id,
                    self._serialize_sse_event(task_update_event),
                )
                return
            except Exception:
                logger.exception(
                    "Distributed SSE publish failed for task %s; "
                    "falling back to local subscribers",
                    task_id,
                )

        async with self.subscriber_lock:
            subscribers = list(self.task_sse_subscribers.get(task_id, ()))
            for subscriber in subscribers:
                await subscriber.put(task_update_event)

    async def dequeue_events_for_sse(
        self, request_id, task_id, sse_event_queue: asyncio.Queue
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        bridge = self.event_bridge_tasks.pop(id(sse_event_queue), None)
        try:
            while True:
                event = await sse_event_queue.get()
                if isinstance(event, JSONRPCError):
                    yield SendTaskStreamingResponse(id=request_id, error=event)
                    break

                yield SendTaskStreamingResponse(id=request_id, result=event)
                if isinstance(event, TaskStatusUpdateEvent) and event.final:
                    break
        finally:
            if bridge is not None:
                bridge.cancel()
                await asyncio.gather(bridge, return_exceptions=True)
            async with self.subscriber_lock:
                if task_id in self.task_sse_subscribers:
                    self.task_sse_subscribers[task_id].remove(sse_event_queue)
