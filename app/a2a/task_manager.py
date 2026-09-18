"""Task manager that connects A2A requests to the multi-agent router."""

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import Any

from app.a2a import utils
from app.a2a.base_task_manager import InMemoryTaskManager
from app.a2a.models import (
    Artifact,
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
    TaskIdParams,
    TaskSendParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from app.a2a.push_notification_auth import PushNotificationSenderAuth
from app.config.constants import SUPPORTED_CONTENT_TYPES


class AgentTaskManager(InMemoryTaskManager):
    def __init__(self, agent: Any, notification_sender_auth: PushNotificationSenderAuth):
        super().__init__()
        self.agent = agent
        self.notification_sender_auth = notification_sender_auth

    async def _run_streaming_agent(self, request: SendTaskStreamingRequest) -> None:
        task_send_params = request.params
        query = self._get_user_query(task_send_params)

        try:
            async for item in self.agent.stream(query, task_send_params.sessionId):
                is_complete = item["is_task_complete"]
                needs_input = item["require_user_input"]
                content = item["content"]
                parts = [{"type": "text", "text": content}]

                if not is_complete and not needs_input:
                    state = TaskState.WORKING
                    message = Message(role="agent", parts=parts)
                    artifact = None
                    final = False
                elif needs_input:
                    state = TaskState.INPUT_REQUIRED
                    message = Message(role="agent", parts=parts)
                    artifact = None
                    final = True
                else:
                    state = TaskState.COMPLETED
                    message = None
                    artifact = Artifact(parts=parts)
                    final = True

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
                        TaskArtifactUpdateEvent(id=task_send_params.id, artifact=artifact),
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
            logging.getLogger(__name__).exception(
                "Streaming agent failed for task %s",
                task_send_params.id,
            )
            await self.enqueue_events_for_sse(
                task_send_params.id,
                InternalError(message="An error occurred while processing the task."),
            )

    def _validate_request(
        self, request: SendTaskRequest | SendTaskStreamingRequest
    ) -> JSONRPCResponse | None:
        params = request.params
        if not utils.are_modalities_compatible(
            params.acceptedOutputModes, SUPPORTED_CONTENT_TYPES
        ):
            return utils.new_incompatible_types_error(request.id)

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

        if request.params.pushNotification:
            verified = await self.set_push_notification_info(
                request.params.id, request.params.pushNotification
            )
            if not verified:
                return SendTaskResponse(
                    id=request.id,
                    error=InvalidParamsError(message="Push notification URL could not be verified"),
                )

        await self.upsert_task(request.params)
        task = await self.update_store(
            request.params.id, TaskStatus(state=TaskState.WORKING), []
        )
        await self.send_task_notification(task)

        try:
            query = self._get_user_query(request.params)
            agent_response = self.agent.invoke(query, request.params.sessionId)
        except Exception:
            logging.getLogger(__name__).exception(
                "Agent invocation failed for task %s", request.params.id
            )
            return SendTaskResponse(
                id=request.id,
                error=InternalError(message="An error occurred while processing the task."),
            )

        return await self._process_agent_response(request, agent_response)

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        error = self._validate_request(request)
        if error:
            return error

        try:
            await self.upsert_task(request.params)
            if request.params.pushNotification:
                verified = await self.set_push_notification_info(
                    request.params.id, request.params.pushNotification
                )
                if not verified:
                    return JSONRPCResponse(
                        id=request.id,
                        error=InvalidParamsError(
                            message="Push notification URL could not be verified"
                        ),
                    )

            queue = await self.setup_sse_consumer(request.params.id)
            asyncio.create_task(self._run_streaming_agent(request))
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
        if agent_response.get("require_user_input", False):
            status = TaskStatus(
                state=TaskState.INPUT_REQUIRED,
                message=Message(role="agent", parts=parts),
            )
            artifacts = None
        else:
            status = TaskStatus(state=TaskState.COMPLETED)
            artifacts = [Artifact(parts=parts)]

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
