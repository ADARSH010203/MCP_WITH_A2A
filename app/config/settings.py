"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return parsed


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return parsed


@dataclass(frozen=True)
class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv(
        "GROQ_MODEL",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    )
    mcp_url: str = os.getenv("MCP_URL", "http://127.0.0.1:3000/sse")
    currency_api_url: str = os.getenv(
        "CURRENCY_API_URL",
        "https://api.frankfurter.dev/v2",
    )
    currency_api_timeout_seconds: float = _env_float(
        "CURRENCY_API_TIMEOUT_SECONDS",
        10.0,
        minimum=0.1,
    )
    a2a_task_db_path: str = os.getenv("A2A_TASK_DB_PATH", ".data/a2a_tasks.db")
    a2a_api_key: str = os.getenv("A2A_API_KEY", "")
    a2a_rate_limit_per_minute: int = _env_int(
        "A2A_RATE_LIMIT_PER_MINUTE",
        60,
        minimum=0,
    )
    a2a_max_concurrent_tasks: int = _env_int(
        "A2A_MAX_CONCURRENT_TASKS",
        8,
        minimum=1,
    )
    a2a_max_input_chars: int = _env_int(
        "A2A_MAX_INPUT_CHARS",
        20000,
        minimum=1,
    )
    a2a_task_retention_days: int = _env_int(
        "A2A_TASK_RETENTION_DAYS",
        30,
        minimum=1,
    )
    push_notification_require_https: bool = _env_bool(
        "PUSH_NOTIFICATION_REQUIRE_HTTPS",
        True,
    )
    push_notification_allow_private_networks: bool = _env_bool(
        "PUSH_NOTIFICATION_ALLOW_PRIVATE_NETWORKS",
        False,
    )


settings = Settings()
