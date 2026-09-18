"""Task manager that connects A2A requests to the multi-agent router."""

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import Any

from app.a2a import utils
from app.a2a.base_task_manager import InMemoryTaskManager
from app.a2a.models import (
    Artifact,
    CancelTaskResponse,
    InternalError,
    InvalidParamsError,
    JSONRPCResponse,
    Message,
    PushNotificationConfig,
    SendTaskRequest,
    SendTaskResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskNotCancelableError,
    TaskNotFoundError,
    TaskSendParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
    UnsupportedOperationError,
)
from app.a2a.push_notification_auth import PushNotificationSenderAuth
from app.a2a.task_store import SQLiteTaskStore
from app.config.constants import SUPPORTED_CONTENT_TYPES
from app.config.settings import settings


class AgentTaskManager(InMemoryTaskManager):
    def __init__(
        self,
        agent: Any,
        notification_sender_auth: PushNotificationSenderAuth,
        store: SQLiteTaskStore | None = None,
    ):
        super().__init__(store=store)
        self.agent = agent
        self.notification_sender_auth = notification_sender_auth
        self.streaming_tasks: dict[str, asyncio.Task[None]] = {}
        self.execution_semaphore = asyncio.Semaphore(
            max(1, settings.a2a_max_concurrent_tasks)
        )

    async def on_set_task_push_notification(self, request: Any):
        config = request.params.pushNotificationConfig
        if not await self.notification_sender_auth.verify_push_notification_url(config.url):
            return JSONRPCResponse(
                id=request.id,
                error=InvalidParamsError(
                    message="Push notification URL could not be verified"
                ),
            )
        return await super().on_set_task_push_notification(request)

    async def on_cancel_task(self, request: Any):
        task_id = request.params.id
        task = await self.get_stored_task(task_id)

        if task is None:
            return CancelTaskResponse(id=request.id, error=TaskNotFoundError())

        if self._is_terminal(task):
            return CancelTaskResponse(id=request.id, error=TaskNotCancelableError())

        running_task = self.streaming_tasks.get(task_id)
        if running_task is None or running_task.done():
            return CancelTaskResponse(id=request.id, error=TaskNotCancelableError())

        current_task = await self.get_stored_task(task_id)
        if current_task is None or self._is_terminal(current_task):
            return CancelTaskResponse(id=request.id, error=TaskNotCancelableError())

        running_task.cancel()
        canceled_status = TaskStatus(
            state=TaskState.CANCELED,
            message=Message(
                role="agent",
                parts=[
                    {
                        "type": "text",
                        "text": "The task was canceled by the client.",
                    }
                ],
            ),
        )
        task = await self.update_store(task_id, canceled_status, [])
        await self.send_task_notification(task)
        await self.enqueue_events_for_sse(
            task_id,
            TaskStatusUpdateEvent(
                id=task_id,
                status=canceled_status,
                final=True,
            ),
        )

        return CancelTaskResponse(id=request.id, result=task)

    async def _run_streaming_agent(self, request: SendTaskStreamingRequest) -> None:
        task_send_params = request.params
        query = self._get_user_query(task_send_params)

        try:
            async with self.execution_semaphore:
                async for item in self.agent.stream(
                    query,
                    task_send_params.sessionId,
                ):
                    status_value = item.get("status", "completed")
                    is_complete = item.get("is_task_complete", False)
                    needs_input = item.get("require_user_input", False)
                    content = (
                        str(item.get("content", "")).strip()
                        or "No response was returned."
                    )

                    if status_value == "error":
                        state = TaskState.FAILED
                        message = Message(
                            role="agent",
                            parts=[{"type": "text", "text": content}],
                        )
                        artifact = None
                        final = True
                    elif needs_input:
                        state = TaskState.INPUT_REQUIRED
                        message = Message(
                            role="agent",
                            parts=[{"type": "text", "text": content}],
                        )
                        artifact = None
                        final = True
                    elif is_complete:
                        state = TaskState.COMPLETED
                        message = None
                        artifact = Artifact(
                            parts=[{"type": "text", "text": content}]
                        )
                        final = True
                    else:
                        state = TaskState.WORKING
                        message = Message(
                            role="agent",
                            parts=[{"type": "text", "text": content}],
                        )
                        artifact = None
                        final = False

                    status = TaskStatus(state=state, message=message)
                    task = await self.update_store(
                        task_send_params.id,
                        status,
                        None if artifact is None else [artifact],
                    )
                    await self.send_task_notification(task)

                    if artifact is not None:
                        await self.enqueue_events_for_sse(
                            task_send_params.id,
                            TaskArtifactUpdateEvent(
                                id=task_send_params.id,
                                artifact=artifact,
                            ),
                        )

                    await self.enqueue_events_for_sse(
                        task_send_params.id,
                        TaskStatusUpdateEvent(
                            id=task_send_params.id,
                            status=status,
                            final=final,
                        ),
                    )
        except Exception:
            logger = logging.getLogger(__name__)
            logger.exception(
                "Streaming agent failed for task %s",
                task_send_params.id,
            )
            failure_status = TaskStatus(
                state=TaskState.FAILED,
                message=Message(
                    role="agent",
                    parts=[
                        {
                            "type": "text",
                            "text": "An error occurred while processing the task.",
                        }
                    ],
                ),
            )
            try:
                task = await self.update_store(
                    task_send_params.id,
                    failure_status,
                    [],
                )
                await self.send_task_notification(task)
            except Exception:
                logger.exception(
                    "Failed to store streaming failure for task %s",
                    task_send_params.id,
                )

            await self.enqueue_events_for_sse(
                task_send_params.id,
                TaskStatusUpdateEvent(
                    id=task_send_params.id,
                    status=failure_status,
                    final=True,
                ),
            )

    def _validate_request(
        self, request: SendTaskRequest | SendTaskStreamingRequest
    ) -> JSONRPCResponse | None:
        params = request.params
        if not utils.are_modalities_compatible(
            params.acceptedOutputModes, SUPPORTED_CONTENT_TYPES
        ):
            return utils.new_incompatible_types_error(request.id)

        if not params.message.parts:
            return JSONRPCResponse(
                id=request.id,
                error=InvalidParamsError(message="A task message is required"),
            )

        first_part = params.message.parts[0]
        if isinstance(first_part, TextPart):
            query = first_part.text.strip()
            if not query:
                return JSONRPCResponse(
                    id=request.id,
                    error=InvalidParamsError(message="Task message cannot be empty"),
                )
            if len(query) > settings.a2a_max_input_chars:
                return JSONRPCResponse(
                    id=request.id,
                    error=InvalidParamsError(
                        message=(
                            "Task message is too large; "
                            f"maximum is {settings.a2a_max_input_chars} characters"
                        )
                    ),
                )

        if params.pushNotification and not params.pushNotification.url:
            return JSONRPCResponse(
                id=request.id,
                error=InvalidParamsError(message="Push notification URL is missing"),
            )
        return None

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        validation_error = self._validate_request(request)
        if validation_error:
            return SendTaskResponse(id=request.id, error=validation_error.error)

        try:
            existing_task, created = await self.get_or_create_task(request.params)
        except ValueError as exc:
            return SendTaskResponse(
                id=request.id,
                error=InvalidParamsError(message=str(exc)),
            )

        if not created:
            return SendTaskResponse(
                id=request.id,
                result=self.append_task_history(
                    existing_task, request.params.historyLength
                ),
            )

        if created and request.params.pushNotification:
            verified = await self.set_push_notification_info(
                request.params.id, request.params.pushNotification
            )
            if not verified:
                failure_status = TaskStatus(
                    state=TaskState.FAILED,
                    message=Message(
                        role="agent",
                        parts=[
                            {
                                "type": "text",
                                "text": "Push notification endpoint verification failed.",
                            }
                        ],
                    ),
                )
                task = await self.update_store(request.params.id, failure_status, [])
                return SendTaskResponse(
                    id=request.id,
                    result=self.append_task_history(
                        task, request.params.historyLength
                    ),
                )

        task = await self.update_store(
            request.params.id, TaskStatus(state=TaskState.WORKING), []
        )
        await self.send_task_notification(task)

        try:
            query = self._get_user_query(request.params)
            async with self.execution_semaphore:
                agent_response = await asyncio.to_thread(
                    self.agent.invoke,
                    query,
                    request.params.sessionId,
                )
        except Exception:
            logging.getLogger(__name__).exception(
                "Agent invocation failed for task %s", request.params.id
            )
            failure_status = TaskStatus(
                state=TaskState.FAILED,
                message=Message(
                    role="agent",
                    parts=[
                        {
                            "type": "text",
                            "text": "An error occurred while processing the task.",
                        }
                    ],
                ),
            )
            task = await self.update_store(request.params.id, failure_status, [])
            await self.send_task_notification(task)
            return SendTaskResponse(id=request.id, result=task)

        return await self._process_agent_response(request, agent_response)

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        error = self._validate_request(request)
        if error:
            return error

        try:
            try:
                existing_task, created = await self.get_or_create_task(request.params)
            except ValueError as exc:
                return JSONRPCResponse(
                    id=request.id,
                    error=InvalidParamsError(message=str(exc)),
                )

            if created and request.params.pushNotification:
                verified = await self.set_push_notification_info(
                    request.params.id, request.params.pushNotification
                )
                if not verified:
                    failure_status = TaskStatus(
                        state=TaskState.FAILED,
                        message=Message(
                            role="agent",
                            parts=[
                                {
                                    "type": "text",
                                    "text": "Push notification endpoint verification failed.",
                                }
                            ],
                        ),
                    )
                    task = await self.update_store(
                        request.params.id,
                        failure_status,
                        [],
                    )
                    queue = await self.setup_sse_consumer(request.params.id)
                    await queue.put(
                        TaskStatusUpdateEvent(
                            id=request.params.id,
                            status=failure_status,
                            final=True,
                        )
                    )
                    return self.dequeue_events_for_sse(
                        request.id,
                        request.params.id,
                        queue,
                    )

            if not created and self._is_terminal(existing_task):
                queue = await self._queue_current_task_state(existing_task)
            else:
                queue = await self.setup_sse_consumer(request.params.id)
                if request.params.id not in self.streaming_tasks:
                    self.streaming_tasks[request.params.id] = asyncio.create_task(
                        self._start_streaming_task(request)
                    )
            return self.dequeue_events_for_sse(request.id, request.params.id, queue)
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to start streaming task %s", request.params.id
            )
            return JSONRPCResponse(
                id=request.id,
                error=InternalError(message="An error occurred while streaming the response"),
            )

    async def _process_agent_response(
        self, request: SendTaskRequest, agent_response: dict[str, Any]
    ) -> SendTaskResponse:
        content = str(agent_response.get("content", "")).strip()
        if not content:
            content = "The agent returned an empty response."

        parts = [{"type": "text", "text": content}]
        response_status = agent_response.get("status", "completed")
        metadata = {
            "agents_used": agent_response.get("agents_used", []),
            "verified": agent_response.get("verified", False),
        }

        if response_status == "input_required":
            status = TaskStatus(
                state=TaskState.INPUT_REQUIRED,
                message=Message(role="agent", parts=parts, metadata=metadata),
            )
            artifacts = None
        elif response_status == "error":
            status = TaskStatus(
                state=TaskState.FAILED,
                message=Message(role="agent", parts=parts, metadata=metadata),
            )
            artifacts = None
        else:
            status = TaskStatus(state=TaskState.COMPLETED)
            artifacts = [Artifact(parts=parts, metadata=metadata)]

        task = await self.update_store(request.params.id, status, artifacts)
        await self.send_task_notification(task)

        return SendTaskResponse(
            id=request.id,
            result=self.append_task_history(task, request.params.historyLength),
        )

    @staticmethod
    def _get_user_query(params: TaskSendParams) -> str:
        part = params.message.parts[0]
        if not isinstance(part, TextPart):
            raise ValueError("Only text parts are supported")
        return part.text

    async def send_task_notification(self, task: Task) -> None:
        if not await self.has_push_notification_info(task.id):
            return
        push_info = await self.get_push_notification_info(task.id)
        await self.notification_sender_auth.send_push_notification(
            push_info.url,
            data=task.model_dump(exclude_none=True),
        )

    async def on_resubscribe_to_task(
        self, request: Any
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        task = await self.get_stored_task(request.params.id)
        if task is None:
            return JSONRPCResponse(
                id=request.id,
                error=TaskNotFoundError(),
            )

        if self._is_terminal(task):
            queue = await self._queue_current_task_state(task)
            return self.dequeue_events_for_sse(request.id, task.id, queue)

        if request.params.id not in self.streaming_tasks:
            return JSONRPCResponse(
                id=request.id,
                error=UnsupportedOperationError(
                    message="This task is active but does not have a resumable streaming worker."
                ),
            )

        try:
            queue = await self.setup_sse_consumer(request.params.id, True)
            return self.dequeue_events_for_sse(request.id, request.params.id, queue)
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to resubscribe to task %s", request.params.id
            )
            return JSONRPCResponse(
                id=request.id,
                error=InternalError(message="An error occurred while reconnecting to stream"),
            )

    async def set_push_notification_info(
        self, task_id: str, config: PushNotificationConfig
    ) -> bool:
        if not await self.notification_sender_auth.verify_push_notification_url(config.url):
            return False
        await super().set_push_notification_info(task_id, config)
        return True
