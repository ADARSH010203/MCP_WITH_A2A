"""Bounded retry policy shared by specialist execution paths."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class RetryPolicy:
    """Compute bounded retry delays without creating retry storms."""

    max_retries: int
    base_delay_seconds: float
    max_delay_seconds: float
    jitter_ratio: float = 0.25
    random_uniform: Callable[[float, float], float] = random.uniform

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be non-negative")
        if self.max_delay_seconds < 0:
            raise ValueError("max_delay_seconds must be non-negative")
        if self.jitter_ratio < 0:
            raise ValueError("jitter_ratio must be non-negative")

    def should_retry(self, retry_index: int) -> bool:
        """Return whether another attempt is allowed after retry_index failures."""
        return 0 <= retry_index < self.max_retries

    def delay(
        self,
        retry_index: int,
        *,
        retry_after_seconds: float | None = None,
    ) -> float:
        """Return the bounded delay before the next attempt."""
        if retry_index < 0:
            raise ValueError("retry_index must be non-negative")

        exponential = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2**retry_index),
        )
        if retry_after_seconds is not None:
            exponential = min(
                self.max_delay_seconds,
                max(exponential, max(0.0, retry_after_seconds)),
            )

        if exponential <= 0 or self.jitter_ratio <= 0:
            return exponential

        jitter = exponential * self.jitter_ratio
        return min(
            self.max_delay_seconds,
            exponential + self.random_uniform(0.0, jitter),
        )
