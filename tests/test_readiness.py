from types import SimpleNamespace

from app.a2a.models import AgentCapabilities, AgentCard, AgentSkill
from app.a2a.readiness import ReadinessChecker


def _settings(**overrides):
    values = {
        "groq_api_key": "groq-secret",
        "a2a_memory_namespace_secret": "memory-secret",
        "a2a_memory_db_path": ":memory:",
        "mcp_url": "http://mcp:3000/sse",
        "a2a_specialist_urls": {},
        "a2a_specialist_api_keys": {},
        "a2a_remote_require_https": True,
        "a2a_remote_require_auth": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _card():
    return AgentCard(
        name="Test Agent",
        url="https://agent.example.com/",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        defaultInputModes=["text"],
        defaultOutputModes=["text"],
        skills=[
            AgentSkill(
                id="code",
                name="Code Specialist",
                tags=["programming"],
            )
        ],
    )


class ReadyTaskManager:
    def is_ready(self):
        return True


def test_readiness_reports_all_critical_dependencies(monkeypatch):
    import app.a2a.readiness as module

    monkeypatch.setattr(module, "settings", _settings())
    class FakeSocket:
        def close(self):
            pass

    monkeypatch.setattr(
        module.socket,
        "create_connection",
        lambda *args, **kwargs: FakeSocket(),
    )

    ready, checks = ReadinessChecker(
        task_manager=ReadyTaskManager(),
        agent_card=_card(),
    ).run()

    assert ready is True
    assert all(item["status"] == "ok" for item in checks.values())
    assert set(checks) == {
        "task_manager",
        "agent_card",
        "groq",
        "memory",
        "task_store",
        "mcp",
        "remote_specialists",
        "event_bus",
    }


def test_readiness_fails_without_memory_namespace_secret(monkeypatch):
    import app.a2a.readiness as module

    monkeypatch.setattr(
        module,
        "settings",
        _settings(a2a_memory_namespace_secret=""),
    )
    class FakeSocket:
        def close(self):
            pass

    monkeypatch.setattr(
        module.socket,
        "create_connection",
        lambda *args, **kwargs: FakeSocket(),
    )

    ready, checks = ReadinessChecker(
        task_manager=ReadyTaskManager(),
        agent_card=_card(),
    ).run()

    assert ready is False
    assert checks["memory"]["status"] == "failed"


def test_readiness_fails_when_mcp_host_is_unreachable(monkeypatch):
    import app.a2a.readiness as module

    monkeypatch.setattr(module, "settings", _settings())
    monkeypatch.setattr(
        module.socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")),
    )

    ready, checks = ReadinessChecker(
        task_manager=ReadyTaskManager(),
        agent_card=_card(),
    ).run()

    assert ready is False
    assert checks["mcp"]["status"] == "failed"


def test_readiness_validates_remote_security_configuration(monkeypatch):
    import app.a2a.readiness as module

    monkeypatch.setattr(
        module,
        "settings",
        _settings(
            a2a_specialist_urls={"code": "http://agent.example.com"},
            a2a_specialist_api_keys={"code": "secret"},
        ),
    )
    monkeypatch.setattr(module.socket, "create_connection", lambda *args, **kwargs: None)

    ready, checks = ReadinessChecker(
        task_manager=ReadyTaskManager(),
        agent_card=_card(),
    ).run()

    assert ready is False
    assert checks["remote_specialists"]["status"] == "failed"
    assert "HTTPS" in checks["remote_specialists"]["detail"]
