from app.mcp.tools.calculator import calculate


def test_calculator_handles_basic_arithmetic():
    assert calculate("10 + 5 * 2")["result"] == 20.0


def test_calculator_supports_parentheses_and_power():
    assert calculate("(2 + 3) ** 3")["result"] == 125.0


def test_calculator_rejects_function_calls():
    try:
        calculate("__import__('os').system('whoami')")
    except ValueError as exc:
        assert "Invalid arithmetic expression" in str(exc)
    else:
        raise AssertionError("Expected function calls to be rejected")


def test_calculator_rejects_overlong_input():
    try:
        calculate("1" * 201)
    except ValueError as exc:
        assert "at most" in str(exc)
    else:
        raise AssertionError("Expected an overlong expression to be rejected")


def test_calculator_rejects_division_by_zero():
    try:
        calculate("10 / 0")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected division by zero to be rejected")
