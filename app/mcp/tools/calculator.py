"""Safe arithmetic calculator exposed as an MCP tool."""

import ast
import operator
from typing import Any


_MAX_EXPRESSION_LENGTH = 200
_BINARY_OPERATORS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)

    if isinstance(node, ast.BinOp):
        operation = _BINARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise ValueError("Unsupported arithmetic operator")
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ValueError("Exponent is too large")
        return operation(left, right)

    if isinstance(node, ast.UnaryOp):
        operation = _UNARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise ValueError("Unsupported unary operator")
        return operation(_evaluate(node.operand))

    raise ValueError("Only numeric arithmetic expressions are supported")


def calculate(expression: str) -> dict[str, Any]:
    """Evaluate a bounded arithmetic expression without dynamic code evaluation."""
    clean_expression = expression.strip()
    if not clean_expression:
        raise ValueError("expression is required")
    if len(clean_expression) > _MAX_EXPRESSION_LENGTH:
        raise ValueError(
            f"expression must be at most {_MAX_EXPRESSION_LENGTH} characters"
        )

    try:
        tree = ast.parse(clean_expression, mode="eval")
        value = _evaluate(tree.body)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("Invalid arithmetic expression") from exc

    if value != value or value in {float("inf"), float("-inf")}:
        raise ValueError("calculation produced a non-finite result")

    return {
        "expression": clean_expression,
        "result": value,
    }
