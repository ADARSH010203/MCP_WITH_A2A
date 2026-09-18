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
    currency_api_timeout_seconds: float = float(
        os.getenv("CURRENCY_API_TIMEOUT_SECONDS", "10")
    )
    a2a_task_db_path: str = os.getenv("A2A_TASK_DB_PATH", ".data/a2a_tasks.db")
    a2a_api_key: str = os.getenv("A2A_API_KEY", "")
    a2a_rate_limit_per_minute: int = int(os.getenv("A2A_RATE_LIMIT_PER_MINUTE", "60"))
    a2a_max_concurrent_tasks: int = int(os.getenv("A2A_MAX_CONCURRENT_TASKS", "8"))
    a2a_max_input_chars: int = int(os.getenv("A2A_MAX_INPUT_CHARS", "20000"))
    a2a_task_retention_days: int = int(os.getenv("A2A_TASK_RETENTION_DAYS", "30"))
    push_notification_require_https: bool = _env_bool(
        "PUSH_NOTIFICATION_REQUIRE_HTTPS",
        True,
    )
    push_notification_allow_private_networks: bool = _env_bool(
        "PUSH_NOTIFICATION_ALLOW_PRIVATE_NETWORKS",
        False,
    )


settings = Settings()
