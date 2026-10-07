from types import SimpleNamespace

import pytest

from app.routing.capability import CapabilityAuthorizationError, CapabilityAuthorizer
from app.routing.registry import DEFAULT_AGENT_REGISTRY
from app.routing.remote_specialist import RemoteA2ASpecialist
from app.routing.workspace import WorkspaceError
from app.memory.sqlite_memory import SQLiteConversationMemory


def test_capability_boundary_rejects_unauthorized_specialist():
    authorizer = CapabilityAuthorizer(
        DEFAULT_AGENT_REGISTRY,
        authorized_agents=("code",),
    )

    with pytest.raises(CapabilityAuthorizationError, match="Unauthorized"):
        authorizer.validate_selection(("email",))


def test_remote_boundary_rejects_plain_http_when_https_required(monkeypatch):
    import app.routing.remote_specialist as module

    monkeypatch.setattr(
        module,
        "settings",
        SimpleNamespace(
            a2a_remote_require_https=True,
            a2a_remote_require_auth=False,
        ),
    )
    agent = RemoteA2ASpecialist(
        agent_type="code",
        url="http://agent.example.com",
    )

    with pytest.raises(ValueError, match="HTTPS"):
        agent._ensure_client()


def test_memory_scope_does_not_store_raw_identity(tmp_path):
    memory = SQLiteConversationMemory(
        str(tmp_path / "memory.db"),
        namespace_secret="safety-secret",
    )
    memory.append(
        "tenant-a",
        "private-session",
        "code",
        "user",
        "private context",
    )
    columns = [
        row[1]
        for row in memory.connection.execute(
            "PRAGMA table_info(conversation_turns)"
        ).fetchall()
    ]
    row = memory.connection.execute(
        "SELECT session_scope_key, scope_key FROM conversation_turns"
    ).fetchone()

    assert "session_id" not in columns
    assert "agent_type" not in columns
    assert all(value not in row for value in ("tenant-a", "private-session", "code"))
    memory.close()


def test_workspace_boundary_rejects_escape(monkeypatch, tmp_path):
    from app.mcp import workspace

    monkeypatch.setattr(
        workspace,
        "settings",
        SimpleNamespace(
            mcp_sandbox_root=str(tmp_path),
            mcp_max_file_bytes=2_000_000,
            mcp_max_output_chars=20_000,
        ),
    )

    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="escapes"):
        workspace.resolve_workspace_path("../outside.txt")
