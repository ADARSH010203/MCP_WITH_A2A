"""Route requests to the project's specialized agents."""

import re
from collections.abc import AsyncIterable
from typing import Any, Protocol

from app.a2a.models import Message
from app.agents.code import CodeGeneratorAgent
from app.agents.currency import CurrencyAgent
from app.agents.deep_learning import DeepLearningAgent
from app.agents.dsa import DsaAgent
from app.agents.email import EmailWriterAgent
from app.agents.game import GameGeneratorAgent
from app.agents.image import ImageGeneratorAgent
from app.agents.reinforcement import ReinforcementLearningAgent


class Agent(Protocol):
    def invoke(self, query: str, session_id: str) -> dict[str, Any]:
        ...

    def stream(self, query: str, session_id: str) -> AsyncIterable[dict[str, Any]]:
        ...


class MultiAgent:
    """Select and run one of the specialized agents."""

    ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("currency", ("currency", "exchange rate", "exchange rates", "forex", "usd", "eur", "gbp")),
        ("email", ("email", "mail", "draft an email", "professional message", "subject line")),
        ("image", ("image", "picture", "photo", "illustration", "generate an image")),
        ("game", ("game", "gameplay", "level design", "character design", "game mechanics")),
        ("deep_learning", ("deep learning", "neural network", "neural networks", "model training", "cnn", "transformer")),
        ("reinforcement", ("reinforcement learning", "reinforcement", "q-learning", "policy gradient")),
        ("dsa", ("dsa", "data structures", "binary search", "sorting", "shortest path", "dynamic programming", "backtracking")),
        ("code", ("code", "program", "function", "class", "script", "algorithm")),
    )

    def __init__(self, agents: dict[str, Agent] | None = None) -> None:
        self.agents = agents or {
            "currency": CurrencyAgent(),
            "email": EmailWriterAgent(),
            "code": CodeGeneratorAgent(),
            "image": ImageGeneratorAgent(),
            "game": GameGeneratorAgent(),
            "deep_learning": DeepLearningAgent(),
            "reinforcement": ReinforcementLearningAgent(),
            "dsa": DsaAgent(),
        }

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.casefold()).strip()

    @classmethod
    def _keyword_matches(cls, text: str, keyword: str) -> bool:
        if " " in keyword or "-" in keyword:
            return keyword in text
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None

    def _detect_agent_type(self, message: Message) -> str:
        if not message.parts:
            return "code"

        first_part = message.parts[0]
        if getattr(first_part, "type", None) != "text":
            return "code"

        text = self._normalize(first_part.text)
        for agent_type, keywords in self.ROUTES:
            if any(self._keyword_matches(text, keyword) for keyword in keywords):
                return agent_type
        return "code"

    def _get_agent(self, agent_type: str) -> Agent:
        try:
            return self.agents[agent_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported agent type: {agent_type}") from exc

    def _route(self, query: str) -> Agent:
        message = Message(role="user", parts=[{"type": "text", "text": query}])
        return self._get_agent(self._detect_agent_type(message))

    def invoke(self, query: str, session_id: str) -> dict[str, Any]:
        return self._route(query).invoke(query, session_id)

    async def stream(self, query: str, session_id: str) -> AsyncIterable[dict[str, Any]]:
        async for response in self._route(query).stream(query, session_id):
            yield response
