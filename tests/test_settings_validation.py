import pytest

from app.config.settings import _env_bool, _env_float


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("FALSE", False),
        ("no", False),
        ("off", False),
    ],
)
def test_env_bool_accepts_known_values(monkeypatch, raw, expected):
    monkeypatch.setenv("TEST_BOOL_SETTING", raw)

    assert _env_bool("TEST_BOOL_SETTING", not expected) is expected


@pytest.mark.parametrize("raw", ["treu", "enabled", "2", "none"])
def test_env_bool_rejects_unrecognized_values(monkeypatch, raw):
    monkeypatch.setenv("TEST_BOOL_SETTING", raw)

    with pytest.raises(ValueError, match="TEST_BOOL_SETTING must be a boolean"):
        _env_bool("TEST_BOOL_SETTING", True)


def test_env_bool_uses_default_for_missing_or_blank_values(monkeypatch):
    monkeypatch.delenv("TEST_BOOL_SETTING", raising=False)
    assert _env_bool("TEST_BOOL_SETTING", True) is True

    monkeypatch.setenv("TEST_BOOL_SETTING", "   ")
    assert _env_bool("TEST_BOOL_SETTING", False) is False


@pytest.mark.parametrize("raw", ["nan", "NaN", "inf", "+inf", "-inf", "Infinity"])
def test_env_float_rejects_non_finite_values(monkeypatch, raw):
    monkeypatch.setenv("TEST_FLOAT_SETTING", raw)

    with pytest.raises(ValueError, match="TEST_FLOAT_SETTING must be a finite number"):
        _env_float("TEST_FLOAT_SETTING", 1.0)


@pytest.mark.parametrize(("raw", "expected"), [("0.0", 0.0), ("12.5", 12.5)])
def test_env_float_accepts_finite_values(monkeypatch, raw, expected):
    monkeypatch.setenv("TEST_FLOAT_SETTING", raw)

    assert _env_float("TEST_FLOAT_SETTING", 1.0) == expected


def test_env_float_still_enforces_minimum(monkeypatch):
    monkeypatch.setenv("TEST_FLOAT_SETTING", "-0.1")

    with pytest.raises(ValueError, match="TEST_FLOAT_SETTING must be >= 0.0"):
        _env_float("TEST_FLOAT_SETTING", 1.0, minimum=0.0)
