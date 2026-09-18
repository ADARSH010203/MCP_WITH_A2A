"""Route user requests to the appropriate specialized agent."""

import re
from typing import AsyncIterable, Callable

from app.a2a.models import Message, Task
from app.agents.currency import CurrencyAgent
from app.agents.specialized import (
    CodeGeneratorAgent,
    DeepLearningAgent,
    DsaAgent,
    EmailWriterAgent,
    GameGeneratorAgent,
    ImageGeneratorAgent,
    RainformentAgent,
)


class MultiAgent:
    """Own and route requests to the specialized agents in this demo."""

    ROUTES: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("currency", ("currency", "exchange rate", "exchange rates", "forex", "usd", "eur", "gbp")),
        ("email", ("email", "mail", "draft an email", "professional message", "subject line")),
        ("image", ("image", "picture", "photo", "illustration", "generate an image")),
        ("game", ("game", "gameplay", "level design", "character design", "game mechanics")),
        ("deep_learning", ("deep learning", "neural network", "neural networks", "model training", "cnn", "transformer")),
        ("rainforment", ("reinforcement learning", "reinforcement", "q-learning", "policy gradient", "game ai")),
        ("dsa", ("dsa", "data structures", "binary search", "sorting", "shortest path", "dynamic programming", "backtracking")),
        ("code", ("code", "program", "function", "class", "script", "algorithm")),
    )

    def __init__(self) -> None:
        self.agents: dict[str, object] = {
            "currency": CurrencyAgent(),
            "email": EmailWriterAgent(),
            "code": CodeGeneratorAgent(),
            "image": ImageGeneratorAgent(),
            "game": GameGeneratorAgent(),
            "deep_learning": DeepLearningAgent(),
            "rainforment": RainformentAgent(),
            "dsa": DsaAgent(),
        }

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.casefold()).strip()

    def _detect_agent_type(self, message: Message) -> str:
        """Select an agent using deterministic keyword matching.

        More specific domains are checked before generic coding terms such as
        'algorithm' and 'model', reducing accidental routing to the code agent.
        """
        if not message.parts:
            return "code"

        text = self._normalize(message.parts[0].text)

        for agent_type, keywords in self.ROUTES:
            if any(keyword in text for keyword in keywords):
                return agent_type

        # The code agent is a more neutral fallback than the previous email fallback.
        return "code"

    def _get_agent(self, agent_type: str):
        try:
            return self.agents[agent_type]
        except KeyError as exc:
            raise ValueError(f"Unsupported agent type: {agent_type}") from exc

    def invoke(self, query: str, session_id: str) -> Task | dict:
        message = Message(
            role="user",
            parts=[{"type": "text", "text": query}],
        )
        agent_type = self._detect_agent_type(message)
        agent = self._get_agent(agent_type)
        return agent.invoke(query, session_id)

    async def stream(self, query: str, session_id: str) -> AsyncIterable[dict]:
        message = Message(
            role="user",
            parts=[{"type": "text", "text": query}],
        )
        agent_type = self._detect_agent_type(message)
        agent = self._get_agent(agent_type)

        async for response in agent.stream(query, session_id):
            yield response
