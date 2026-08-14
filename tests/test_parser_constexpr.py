"""Parser regression tests for compile-time constant expressions.

These tests verify folding behavior for integer and float constant expressions,
including Q16.16 encoding and divide/modulo-by-zero diagnostics.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hasc import ast
from hasc import parser as has_parser


def _const_by_name(module: ast.Module, name: str) -> ast.ConstDecl:
    for item in module.items:
        if isinstance(item, ast.ConstDecl) and item.name == name:
            return item
        if hasattr(item, "items"):
            for child in item.items:
                if isinstance(child, ast.ConstDecl) and child.name == name:
                    return child
    raise AssertionError(f"Const '{name}' not found")


def test_const_expression_can_reference_previous_constant():
    mod = has_parser.parse("const MY_VAL = 1; const MY_VAL2 = MY_VAL + 1;")

    assert _const_by_name(mod, "MY_VAL2").value == 2


def test_const_expression_can_chain_previous_constants():
    mod = has_parser.parse(
        "const BASE = 2; const OFFSET = BASE + 3; const SIZE = OFFSET * 4;"
    )

    assert _const_by_name(mod, "SIZE").value == 20


def test_constexpr_integer_precedence_folds_correctly():
    mod = has_parser.parse("const A = 2 + 3 * 4;")
    c = _const_by_name(mod, "A")
    assert c.value == 14
    assert c.is_q16 is False


def test_constexpr_parentheses_override_precedence():
    mod = has_parser.parse("const A = (2 + 3) * 4;")
    c = _const_by_name(mod, "A")
    assert c.value == 20
    assert c.is_q16 is False


def test_constexpr_unary_negation_folds_correctly():
    mod = has_parser.parse("const NEG = -5 + 2;")
    c = _const_by_name(mod, "NEG")
    assert c.value == -3
    assert c.is_q16 is False


def test_constexpr_integer_division_uses_flooring_semantics():
    mod = has_parser.parse("const D = 7 / 2;")
    c = _const_by_name(mod, "D")
    assert c.value == 3
    assert c.is_q16 is False


def test_constexpr_modulo_folds_correctly():
    mod = has_parser.parse("const M = 10 % 3;")
    c = _const_by_name(mod, "M")
    assert c.value == 1
    assert c.is_q16 is False


def test_constexpr_float_expression_encodes_to_q16():
    mod = has_parser.parse("const F = (2.5 + 0.5) * 2;")
    c = _const_by_name(mod, "F")
    assert c.value == 393216  # 6.0 * 65536
    assert c.is_q16 is True


def test_constexpr_mixed_float_int_division_encodes_to_q16():
    mod = has_parser.parse("const F = 7 / 2.0;")
    c = _const_by_name(mod, "F")
    assert c.value == 229376  # 3.5 * 65536
    assert c.is_q16 is True


def test_constexpr_division_by_zero_reports_error():
    with pytest.raises(
        SyntaxError,
        match=r"Constant expression error in const 'BAD' at line 1, column \d+: Division by zero in constant expression",
    ):
        has_parser.parse("const BAD = 10 / 0;")


def test_constexpr_modulo_by_zero_reports_error():
    with pytest.raises(
        SyntaxError,
        match=r"Constant expression error in const 'BAD' at line 1, column \d+: Modulo by zero in constant expression",
    ):
        has_parser.parse("const BAD = 10 % 0;")
