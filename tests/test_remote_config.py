import pytest

from app.config.settings import _load_specialist_urls


def test_load_specialist_urls_parses_multiple_agents(monkeypatch):
    monkeypatch.setenv(
        "A2A_SPECIALIST_URLS",
        "code=http://127.0.0.1:8101;deep_learning=https://agent.example.com/dl",
    )

    assert _load_specialist_urls() == {
        "code": "http://127.0.0.1:8101",
        "deep_learning": "https://agent.example.com/dl",
    }


def test_load_specialist_urls_rejects_invalid_entries(monkeypatch):
    monkeypatch.setenv("A2A_SPECIALIST_URLS", "code=not-a-url")

    with pytest.raises(ValueError, match="invalid"):
        _load_specialist_urls()


def test_load_specialist_urls_rejects_embedded_credentials(monkeypatch):
    monkeypatch.setenv(
        "A2A_SPECIALIST_URLS",
        "code=https://user:pass@example.com",
    )

    with pytest.raises(ValueError, match="embedded credentials"):
        _load_specialist_urls()


def test_load_specialist_urls_rejects_duplicate_agent_types(monkeypatch):
    monkeypatch.setenv(
        "A2A_SPECIALIST_URLS",
        "code=http://127.0.0.1:8101;code=http://127.0.0.1:8102",
    )

    with pytest.raises(ValueError, match="duplicate agent type"):
        _load_specialist_urls()


def test_load_specialist_api_keys_parses_and_rejects_duplicates(monkeypatch):
    from app.config.settings import _load_specialist_api_keys

    monkeypatch.setenv(
        "A2A_SPECIALIST_API_KEYS",
        "code=code-secret;deep_learning=dl-secret",
    )
    assert _load_specialist_api_keys() == {
        "code": "code-secret",
        "deep_learning": "dl-secret",
    }

    monkeypatch.setenv("A2A_SPECIALIST_API_KEYS", "code=one;code=two")
    with pytest.raises(ValueError, match="duplicate agent type"):
        _load_specialist_api_keys()


def test_load_specialist_api_keys_rejects_empty_values(monkeypatch):
    from app.config.settings import _load_specialist_api_keys

    monkeypatch.setenv("A2A_SPECIALIST_API_KEYS", "code=")
    with pytest.raises(ValueError, match="non-empty"):
        _load_specialist_api_keys()
