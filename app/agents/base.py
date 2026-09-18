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
from app.memory.sqlite_memory import SQLiteConversationMemory


class ResponseFormat(BaseModel):
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


class BaseAgent:
    SYSTEM_INSTRUCTION = "You are a helpful specialized assistant."
    processing_message = "Processing your request..."
    memory_agent_type = "base"

    def _memory_context(self, session_id: str) -> str:
        return self.memory_store.format_context(session_id, self.memory_agent_type)

    def _prepare_query(self, query: str, session_id: str) -> str:
        context = self._memory_context(session_id)
        if not context:
            return query
        return f"{context}\n\nCurrent user request:\n{query}"

    def _remember(self, session_id: str, query: str, response: dict[str, Any]) -> None:
        self.memory_store.append(session_id, self.memory_agent_type, "user", query)
        content = str(response.get("content", "")).strip()
        if content:
            self.memory_store.append(
                session_id,
                self.memory_agent_type,
                "assistant",
                content,
            )
    supported_content_types = SUPPORTED_CONTENT_TYPES

    def __init__(self) -> None:
        if self.memory_agent_type == "base":
            self.memory_agent_type = self.__class__.__module__.rsplit(".", 1)[-1]
        self.memory_store = SQLiteConversationMemory(
            settings.a2a_memory_db_path,
            max_turns=settings.a2a_memory_turns,
            max_chars=settings.a2a_memory_max_chars,
        )
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
        prepared_query = self._prepare_query(query, session_id)
        self.graph.invoke({"messages": [("user", prepared_query)]}, config)
        response = self.get_agent_response(config)
        self._remember(session_id, query, response)
        return response

    async def stream(
        self, query: str, session_id: str
    ) -> AsyncIterable[dict[str, Any]]:
        config = self._config(session_id)

        prepared_query = self._prepare_query(query, session_id)
        async for item in self.graph.astream(
            {"messages": [("user", prepared_query)]},
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

        response = self.get_agent_response(config)
        self._remember(session_id, query, response)
        yield response

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
