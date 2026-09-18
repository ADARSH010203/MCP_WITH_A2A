from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_compose_file_is_valid_yaml():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert set(compose["services"]) == {"mcp", "a2a"}
    assert compose["services"]["a2a"]["environment"]["MCP_URL"] == "http://mcp:3000/sse"
    assert compose["services"]["a2a"]["healthcheck"]["retries"] == 3


def test_dockerfile_runs_as_non_root():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
