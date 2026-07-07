from __future__ import annotations

import ast
import re
from decimal import Decimal, InvalidOperation


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def _format_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return f"{value:.0f}"
    return format(value, "f").rstrip("0").rstrip(".")


def _normalize_numeric_text(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw or raw.upper() in {"NA", "NAN"}:
        return None
    normalized = re.sub(r"\s+", "", raw.upper().replace(",", ""))
    match = re.fullmatch(
        r"([+-]?\d+(?:\.\d+)?)(箱|件|PCS?|PICES?|CARTONS?|CTNS?|PALLETS?|PLTS?|KGS?|CBM)?",
        normalized,
    )
    if not match:
        return None
    return _format_decimal(Decimal(match.group(1)))


def _decimal_from_number_node(node: ast.AST) -> Decimal | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _decimal_from_number_node(node.operand)
        if operand is None:
            return None
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _decimal_from_number_node(node.left)
        right = _decimal_from_number_node(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            return None
        return left / right
    return None


def _parse_simple_numeric_expression(value: str) -> str | None:
    expression = re.sub(r"\s+", "", (value or "").replace(",", "").replace("×", "*"))
    if not expression or not any(operator in expression for operator in "+-*/()"):
        return None
    if not re.fullmatch(r"[0-9+\-*/().]+", expression):
        return None
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None
    result = _decimal_from_number_node(parsed.body)
    if result is None or result <= 0:
        return None
    return _format_decimal(result)


def _parse_per_box_expression(value: str) -> str | None:
    raw = re.sub(r"\s+", "", value.upper().replace(",", ""))
    has_expression_signal = any(part in raw for part in ("K", "CARTON", "CTN", "+", "*"))
    if not raw or not has_expression_signal:
        return None

    expression = raw.replace("×", "*")
    expression = re.sub(r"CARTONS?|CTNS?", "", expression)
    if not re.fullmatch(r"[0-9K+*.]+", expression):
        return None

    total = Decimal("0")
    for term in expression.split("+"):
        if not term:
            return None
        product = Decimal("1")
        for factor in term.split("*"):
            factor_match = re.fullmatch(r"(\d+(?:\.\d+)?)(K?)", factor)
            if not factor_match:
                return None
            number = Decimal(factor_match.group(1))
            if factor_match.group(2):
                number *= Decimal("1000")
            product *= number
        total += product

    if total <= 0:
        return None
    return _format_decimal(total)


def _per_box_number_satisfies_rule(per_box_number: Decimal | None, min_package: str) -> bool:
    if per_box_number is None or per_box_number <= 0:
        return False
    min_package_number = _decimal(min_package) if min_package else None
    if min_package_number is None or min_package_number == 0:
        return True
    return per_box_number >= min_package_number and per_box_number % min_package_number == 0
