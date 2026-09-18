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
    a2a_task_db_path: str = os.getenv("A2A_TASK_DB_PATH", ".data/a2a_tasks.db")
    a2a_api_key: str = os.getenv("A2A_API_KEY", "")
    push_notification_require_https: bool = _env_bool(
        "PUSH_NOTIFICATION_REQUIRE_HTTPS",
        True,
    )
    push_notification_allow_private_networks: bool = _env_bool(
        "PUSH_NOTIFICATION_ALLOW_PRIVATE_NETWORKS",
        False,
    )


settings = Settings()
