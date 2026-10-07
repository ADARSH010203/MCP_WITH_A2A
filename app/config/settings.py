"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass, field

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
    a2a_semantic_routing_enabled: bool = _env_bool(
        "A2A_SEMANTIC_ROUTING_ENABLED",
        True,
    )
    a2a_semantic_routing_min_score: float = _env_float(
        "A2A_SEMANTIC_ROUTING_MIN_SCORE",
        0.58,
        minimum=0.0,
    )
    a2a_semantic_routing_secondary_score: float = _env_float(
        "A2A_SEMANTIC_ROUTING_SECONDARY_SCORE",
        0.72,
        minimum=0.0,
    )
    a2a_semantic_routing_max_agents: int = _env_int(
        "A2A_SEMANTIC_ROUTING_MAX_AGENTS",
        3,
        minimum=1,
    )
    a2a_allowed_agents: tuple[str, ...] = field(default_factory=tuple, init=False)
    mcp_url: str = os.getenv("MCP_URL", "http://127.0.0.1:3000/sse")
    a2a_public_url: str = os.getenv("A2A_PUBLIC_URL", "")
    a2a_cors_origins: tuple[str, ...] = field(default_factory=tuple, init=False)
    a2a_specialist_urls: dict[str, str] = field(default_factory=dict, init=False)
    a2a_specialist_api_keys: dict[str, str] = field(default_factory=dict, init=False)
    a2a_remote_connect_timeout_seconds: float = _env_float(
        "A2A_REMOTE_CONNECT_TIMEOUT_SECONDS",
        10.0,
        minimum=0.1,
    )
    a2a_remote_request_timeout_seconds: float = _env_float(
        "A2A_REMOTE_REQUEST_TIMEOUT_SECONDS",
        55.0,
        minimum=0.1,
    )
    a2a_remote_require_https: bool = _env_bool(
        "A2A_REMOTE_REQUIRE_HTTPS",
        True,
    )
    a2a_remote_require_auth: bool = _env_bool(
        "A2A_REMOTE_REQUIRE_AUTH",
        True,
    )
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
    a2a_max_collaborative_agents: int = _env_int(
        "A2A_MAX_COLLABORATIVE_AGENTS",
        3,
        minimum=1,
    )
    a2a_max_input_chars: int = _env_int(
        "A2A_MAX_INPUT_CHARS",
        20000,
        minimum=1,
    )
    a2a_max_request_body_bytes: int = _env_int(
        "A2A_MAX_REQUEST_BODY_BYTES",
        1_000_000,
        minimum=1024,
    )
    a2a_max_task_id_chars: int = _env_int(
        "A2A_MAX_TASK_ID_CHARS",
        128,
        minimum=1,
    )
    a2a_max_session_id_chars: int = _env_int(
        "A2A_MAX_SESSION_ID_CHARS",
        128,
        minimum=1,
    )
    a2a_task_retention_days: int = _env_int(
        "A2A_TASK_RETENTION_DAYS",
        30,
        minimum=0,
    )
    a2a_memory_db_path: str = os.getenv(
        "A2A_MEMORY_DB_PATH",
        ".data/a2a_memory.db",
    )
    a2a_memory_turns: int = _env_int(
        "A2A_MEMORY_TURNS",
        8,
        minimum=1,
    )
    a2a_memory_max_chars: int = _env_int(
        "A2A_MEMORY_MAX_CHARS",
        4000,
        minimum=100,
    )
    a2a_memory_namespace_secret: str = os.getenv(
        "A2A_MEMORY_NAMESPACE_SECRET",
        "",
    )
    a2a_memory_retention_days: int = _env_int(
        "A2A_MEMORY_RETENTION_DAYS",
        30,
        minimum=0,
    )
    a2a_specialist_timeout_seconds: float = _env_float(
        "A2A_SPECIALIST_TIMEOUT_SECONDS",
        45.0,
        minimum=0.1,
    )
    a2a_specialist_max_retries: int = _env_int(
        "A2A_SPECIALIST_MAX_RETRIES",
        1,
        minimum=0,
    )
    a2a_specialist_retry_backoff_seconds: float = _env_float(
        "A2A_SPECIALIST_RETRY_BACKOFF_SECONDS",
        0.25,
        minimum=0.0,
    )
    a2a_specialist_retry_max_backoff_seconds: float = _env_float(
        "A2A_SPECIALIST_RETRY_MAX_BACKOFF_SECONDS",
        5.0,
        minimum=0.0,
    )
    a2a_specialist_retry_jitter_ratio: float = _env_float(
        "A2A_SPECIALIST_RETRY_JITTER_RATIO",
        0.25,
        minimum=0.0,
    )
    a2a_specialist_total_timeout_seconds: float = _env_float(
        "A2A_SPECIALIST_TOTAL_TIMEOUT_SECONDS",
        90.0,
        minimum=0.1,
    )
    a2a_max_agent_calls_per_task: int = _env_int(
        "A2A_MAX_AGENT_CALLS_PER_TASK",
        6,
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


def _load_specialist_urls() -> dict[str, str]:
    raw = os.getenv("A2A_SPECIALIST_URLS", "")
    if not raw.strip():
        return {}

    from urllib.parse import urlparse

    result: dict[str, str] = {}
    for entry in raw.split(";"):
        item = entry.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(
                "A2A_SPECIALIST_URLS entries must use agent_type=url format"
            )

        agent_type, url = (part.strip() for part in item.split("=", 1))
        parsed = urlparse(url)
        if not agent_type or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                "A2A_SPECIALIST_URLS contains an invalid agent_type or URL"
            )
        if agent_type in result:
            raise ValueError(
                f"A2A_SPECIALIST_URLS contains duplicate agent type: {agent_type}"
            )
        if parsed.username or parsed.password:
            raise ValueError(
                "A2A_SPECIALIST_URLS URLs must not contain embedded credentials"
            )
        result[agent_type] = url.rstrip("/")

    return result


def _load_specialist_api_keys() -> dict[str, str]:
    raw = os.getenv("A2A_SPECIALIST_API_KEYS", "")
    if not raw.strip():
        return {}

    result: dict[str, str] = {}
    for entry in raw.split(";"):
        item = entry.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(
                "A2A_SPECIALIST_API_KEYS entries must use agent_type=key format"
            )

        agent_type, api_key = (part.strip() for part in item.split("=", 1))
        if not agent_type or not api_key:
            raise ValueError(
                "A2A_SPECIALIST_API_KEYS entries must contain a non-empty agent type and key"
            )
        if agent_type in result:
            raise ValueError(
                f"A2A_SPECIALIST_API_KEYS contains duplicate agent type: {agent_type}"
            )
        result[agent_type] = api_key

    return result


def _load_allowed_agents() -> tuple[str, ...]:
    raw = os.getenv("A2A_ALLOWED_AGENTS", "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _load_cors_origins() -> tuple[str, ...]:
    raw = os.getenv("A2A_CORS_ORIGINS", "")
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


settings = Settings()
object.__setattr__(settings, "a2a_specialist_urls", _load_specialist_urls())
object.__setattr__(settings, "a2a_specialist_api_keys", _load_specialist_api_keys())
object.__setattr__(settings, "a2a_allowed_agents", _load_allowed_agents())
object.__setattr__(settings, "a2a_cors_origins", _load_cors_origins())
