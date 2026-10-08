from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_compose_file_is_valid_yaml():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert set(compose["services"]) == {"mcp", "a2a"}
    assert compose["services"]["a2a"]["environment"]["MCP_URL"] == "http://mcp:3000/sse"
    assert compose["services"]["a2a"]["healthcheck"]["retries"] == 3
    environment = compose["services"]["a2a"]["environment"]
    assert "A2A_MEMORY_NAMESPACE_SECRET" in environment
    assert "A2A_REMOTE_REQUIRE_HTTPS" in environment
    assert "A2A_SPECIALIST_TOTAL_TIMEOUT_SECONDS" in environment
    assert "A2A_EVENT_BUS_BACKEND" in environment
    assert "A2A_EVENT_BUS_URL" in environment
    assert "MCP_SANDBOX_ROOT" in compose["services"]["a2a"]["environment"]
    assert "MCP_ALLOWED_TOOLS" in compose["services"]["mcp"]["environment"]


def test_mcp_service_mounts_bounded_workspace():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    mcp_service = compose["services"]["mcp"]

    assert any("/app/workspace" in item.get("volume", item) if isinstance(item, dict) else "/app/workspace" in item for item in mcp_service.get("volumes", []))


def test_dockerfile_runs_as_non_root():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_redis_profile_is_declared():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    redis_service = compose["services"]["redis"]
    assert redis_service["image"] == "redis:7-alpine"
    assert "distributed" in redis_service["profiles"]
    assert "6379" in redis_service["expose"]
    assert "redis_data" in redis_service["volumes"][0]
