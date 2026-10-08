"""Token usage accounting and configurable cost governance."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.observability.metrics import METRICS


@dataclass(frozen=True)
class TokenUsage:
    """Token usage observed from one provider response."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @classmethod
    def from_message(cls, message: Any) -> TokenUsage | None:
        """Extract usage from common LangChain AIMessage metadata shapes."""
        metadata = getattr(message, "usage_metadata", None)
        if metadata is None:
            response_metadata = getattr(message, "response_metadata", None)
            if isinstance(response_metadata, dict):
                metadata = response_metadata.get("token_usage")

        if not isinstance(metadata, dict):
            return None

        input_tokens = metadata.get(
            "input_tokens",
            metadata.get("prompt_tokens", 0),
        )
        output_tokens = metadata.get(
            "output_tokens",
            metadata.get("completion_tokens", 0),
        )

        try:
            input_value = max(0, int(input_tokens))
            output_value = max(0, int(output_tokens))
        except (TypeError, ValueError):
            return None

        if input_value == 0 and output_value == 0:
            return None

        return cls(
            input_tokens=input_value,
            output_tokens=output_value,
        )

    @classmethod
    def from_messages(cls, messages: list[Any]) -> TokenUsage:
        """Aggregate usage from newly produced model messages only."""
        input_tokens = 0
        output_tokens = 0

        for message in messages:
            if usage := cls.from_message(message):
                input_tokens += usage.input_tokens
                output_tokens += usage.output_tokens

        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class CostPolicy:
    """Operator-configured token and USD limits."""

    input_usd_per_1m_tokens: float = 0.0
    output_usd_per_1m_tokens: float = 0.0
    max_total_tokens_per_task: int = 0
    max_estimated_cost_usd_per_task: float = 0.0

    def estimate(self, usage: TokenUsage) -> float:
        return (
            usage.input_tokens * self.input_usd_per_1m_tokens
            + usage.output_tokens * self.output_usd_per_1m_tokens
        ) / 1_000_000

    def exceeds(
        self,
        usage: TokenUsage,
        estimated_cost_usd: float,
    ) -> bool:
        token_limit = (
            self.max_total_tokens_per_task > 0
            and usage.total_tokens > self.max_total_tokens_per_task
        )
        cost_limit = (
            self.max_estimated_cost_usd_per_task > 0
            and estimated_cost_usd > self.max_estimated_cost_usd_per_task
        )
        return token_limit or cost_limit


class CostBudget:
    """Thread-safe aggregate token/cost budget for one top-level task."""

    def __init__(self, policy: CostPolicy) -> None:
        self.policy = policy
        self.usage = TokenUsage()
        self.estimated_cost_usd = 0.0
        self.exceeded = False
        self._lock = Lock()

    def record(
        self,
        usage: TokenUsage | None,
        *,
        agent: str,
        execution_mode: str,
    ) -> bool:
        if usage is None or usage.total_tokens == 0:
            METRICS.increment(
                "llm_usage_missing_total",
                labels={"agent": agent},
            )
            return not self.exceeded

        with self._lock:
            self.usage = TokenUsage(
                input_tokens=self.usage.input_tokens + usage.input_tokens,
                output_tokens=self.usage.output_tokens + usage.output_tokens,
            )
            self.estimated_cost_usd += self.policy.estimate(usage)
            self.exceeded = self.policy.exceeds(
                self.usage,
                self.estimated_cost_usd,
            )
            exceeded = self.exceeded

        METRICS.increment(
            "llm_input_tokens_total",
            usage.input_tokens,
            labels={"agent": agent, "mode": execution_mode},
        )
        METRICS.increment(
            "llm_output_tokens_total",
            usage.output_tokens,
            labels={"agent": agent, "mode": execution_mode},
        )
        METRICS.observe(
            "llm_estimated_cost_usd",
            self.estimated_cost_usd,
        )

        if exceeded:
            METRICS.increment(
                "llm_cost_budget_exceeded_total",
                labels={"agent": agent},
            )

        return not exceeded

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self.usage.to_dict(),
                "estimated_cost_usd": round(self.estimated_cost_usd, 8),
                "budget_exceeded": self.exceeded,
                "max_total_tokens_per_task": (
                    self.policy.max_total_tokens_per_task
                ),
                "max_estimated_cost_usd_per_task": (
                    self.policy.max_estimated_cost_usd_per_task
                ),
            }
