"""Currency specialist backed by the project's MCP currency server."""

import asyncio
import threading
from collections.abc import AsyncIterable
from typing import Any, Literal

from langchain_core.messages import AIMessage, ToolMessage
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient  # type: ignore
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

from app.config.settings import settings
from app.memory.sqlite_memory import SQLiteConversationMemory


def _fetch_mcp_tools_sync() -> list[Any]:
    """Fetch MCP tools from a sync context, including an active event-loop context."""

    servers_config = {
        "currency_server": {
            "transport": "sse",
            "url": settings.mcp_url,
        }
    }

    async def _fetch_tools() -> list[Any]:
        async with MultiServerMCPClient(servers_config) as client:
            return client.get_tools()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_fetch_tools())

    result: list[Any] = []
    error: list[BaseException] = []

    def runner() -> None:
        try:
            result.extend(asyncio.run(_fetch_tools()))
        except BaseException as exc:
            error.append(exc)

    thread = threading.Thread(target=runner, name="mcp-tool-loader")
    thread.start()
    thread.join()

    if error:
        raise RuntimeError("Unable to initialize the currency MCP tools") from error[0]

    return result


class ResponseFormat(BaseModel):
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


class CurrencyAgent:
    memory_agent_type = "currency"
    """Answer currency requests using the remote MCP exchange-rate tool."""

    SYSTEM_INSTRUCTION = (
        "You are a specialized assistant for currency conversions. "
        "Use the 'get_exchange_rate' tool for currency exchange-rate questions. "
        "The tool returns daily reference rates; do not describe them as guaranteed live-trading prices. "
        "Do not answer unrelated topics. "
        "Set response status to input_required when more information is needed, "
        "error when processing fails, and completed when the request is complete."
    )

    def __init__(self) -> None:
        self.memory_store = SQLiteConversationMemory(
            settings.a2a_memory_db_path,
            max_turns=settings.a2a_memory_turns,
            max_chars=settings.a2a_memory_max_chars,
        )
        self.tools = _fetch_mcp_tools_sync()
        self.model = ChatGroq(model=settings.groq_model, max_tokens=2048)
        self.memory = MemorySaver()
        self.graph = create_react_agent(
            self.model,
            tools=self.tools,
            checkpointer=self.memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=ResponseFormat,
        )

    def invoke(self, query: str, session_id: str) -> dict[str, Any]:
        config = {"configurable": {"thread_id": session_id}}
        context = self.memory_store.format_context(session_id, self.memory_agent_type)
        prepared_query = query if not context else f"{context}\n\nCurrent user request:\n{query}"
        self.graph.invoke({"messages": [("user", prepared_query)]}, config)
        response = self.get_agent_response(config)
        self._remember(session_id, query, response)
        return response

    def _remember(self, session_id: str, query: str, response: dict[str, Any]) -> None:
        self.memory_store.append(session_id, self.memory_agent_type, "user", query)
        content = str(response.get("content", "")).strip()
        if content:
            self.memory_store.append(session_id, self.memory_agent_type, "assistant", content)

    async def stream(
        self, query: str, session_id: str
    ) -> AsyncIterable[dict[str, Any]]:
        config = {"configurable": {"thread_id": session_id}}

        async for item in self.graph.astream(
            {"messages": [("user", query)]},
            config,
            stream_mode="values",
        ):
            message = item["messages"][-1]
            if isinstance(message, AIMessage) and message.tool_calls:
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "status": "working",
                    "content": "Looking up the exchange rates...",
                }
            elif isinstance(message, ToolMessage):
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "status": "working",
                    "content": "Processing the exchange rates...",
                }

        response = self.get_agent_response(config)
        self._remember(session_id, query, response)
        yield response

    def get_agent_response(self, config: dict[str, Any]) -> dict[str, Any]:
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get("structured_response")

        if isinstance(structured_response, ResponseFormat):
            if structured_response.status == "completed":
                return {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "status": "completed",
                    "content": structured_response.message,
                }

            if structured_response.status == "input_required":
                return {
                    "is_task_complete": False,
                    "require_user_input": True,
                    "status": "input_required",
                    "content": structured_response.message,
                }

            return {
                "is_task_complete": False,
                "require_user_input": False,
                "status": "error",
                "content": structured_response.message,
            }

        return {
            "is_task_complete": False,
            "require_user_input": False,
            "status": "error",
            "content": "We are unable to process your request at the moment. Please try again.",
        }

    supported_content_types = ["text", "text/plain"]
