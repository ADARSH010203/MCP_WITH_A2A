"""Shared implementation for specialized LLM agents."""

from collections.abc import AsyncIterable
from typing import Any, Literal

from langchain_core.messages import AIMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

from app.config.constants import SUPPORTED_CONTENT_TYPES
from app.config.settings import settings


class ResponseFormat(BaseModel):
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


class BaseAgent:
    SYSTEM_INSTRUCTION = "You are a helpful specialized assistant."
    processing_message = "Processing your request..."
    supported_content_types = SUPPORTED_CONTENT_TYPES

    def __init__(self) -> None:
        self.model = ChatGroq(model=settings.groq_model, max_tokens=2048)
        self.memory = MemorySaver()
        self.graph = create_react_agent(
            self.model,
            tools=[],
            checkpointer=self.memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=ResponseFormat,
        )

    def _config(self, session_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": session_id}}

    def invoke(self, query: str, session_id: str) -> dict[str, Any]:
        config = self._config(session_id)
        self.graph.invoke({"messages": [("user", query)]}, config)
        return self.get_agent_response(config)

    async def stream(
        self, query: str, session_id: str
    ) -> AsyncIterable[dict[str, Any]]:
        config = self._config(session_id)

        async for item in self.graph.astream(
            {"messages": [("user", query)]},
            config,
            stream_mode="values",
        ):
            message = item["messages"][-1]
            if isinstance(message, ToolMessage) or (
                isinstance(message, AIMessage) and message.tool_calls
            ):
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "status": "working",
                    "content": self.processing_message,
                }

        yield self.get_agent_response(config)

    def get_agent_response(self, config: dict[str, Any]) -> dict[str, Any]:
        state = self.graph.get_state(config)
        response = state.values.get("structured_response")

        if isinstance(response, ResponseFormat):
            if response.status == "completed":
                return {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "status": "completed",
                    "content": response.message,
                }

            if response.status == "input_required":
                return {
                    "is_task_complete": False,
                    "require_user_input": True,
                    "status": "input_required",
                    "content": response.message,
                }

            return {
                "is_task_complete": False,
                "require_user_input": False,
                "status": "error",
                "content": response.message,
            }

        return {
            "is_task_complete": False,
            "require_user_input": False,
            "status": "error",
            "content": "We are unable to process your request at the moment. Please try again.",
        }
