"""Parser regression tests for #ifdef/#ifndef conditional compilation directives."""

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


def test_ifdef_true_when_const_equals_one():
    src = """
const FEATURE = 1;
#ifdef FEATURE
const X = 10;
#else
const X = 20;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "X").value == 10


def test_ifdef_true_when_const_defined_with_any_value():
    src = """
const FEATURE = 0;
#ifdef FEATURE
const X = 10;
#else
const X = 20;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "X").value == 10

    src2 = """
const FEATURE = 5;
#ifdef FEATURE
const X = 10;
#else
const X = 20;
#endif
"""
    mod2 = has_parser.parse(src2)
    assert _const_by_name(mod2, "X").value == 10

    src3 = """
#ifdef FEATURE
const X = 10;
#else
const X = 20;
#endif
"""
    mod3 = has_parser.parse(src3)
    assert _const_by_name(mod3, "X").value == 20


def test_ifndef_true_when_symbol_undefined():
    src = """
#ifndef FEATURE
const X = 1;
#else
const X = 2;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "X").value == 1


def test_nested_conditionals_select_expected_branch():
    src = """
const OUTER = 1;
const INNER = 0;
#ifdef OUTER
  #ifdef INNER
  const SEL = 11;
  #else
  const SEL = 12;
  #endif
#else
const SEL = 13;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "SEL").value == 11


def test_inactive_else_branch_with_invalid_syntax_is_ignored():
    src = """
const FEATURE = 1;
#ifdef FEATURE
const OK = 7;
#else
const BROKEN = ;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "OK").value == 7


def test_else_without_if_reports_preprocessor_error():
    with pytest.raises(
        SyntaxError,
        match=r"Preprocessor error at line 2: '#else' without matching '#ifdef/#ifndef/#if'",
    ):
        has_parser.parse("\n#else\nconst X = 1;\n")


def test_endif_without_if_reports_preprocessor_error():
    with pytest.raises(
        SyntaxError,
        match=r"Preprocessor error at line 2: '#endif' without matching '#ifdef/#ifndef/#if'",
    ):
        has_parser.parse("\n#endif\n")


def test_double_else_reports_preprocessor_error():
    src = """
#ifdef A
const X = 1;
#else
const X = 2;
#else
const X = 3;
#endif
"""
    with pytest.raises(SyntaxError, match=r"multiple '#else' for conditional opened at line 2"):
        has_parser.parse(src)


def test_unterminated_ifdef_reports_preprocessor_error():
    src = """
#ifdef A
const X = 1;
"""
    with pytest.raises(SyntaxError, match=r"unterminated '#ifdef A' opened at line 2"):
        has_parser.parse(src)


def test_ifdef_uses_folded_const_expression_value():
    src = """
const FEATURE = 2 - 1;
#ifdef FEATURE
const X = 42;
#else
const X = 0;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "X").value == 42


def test_active_branch_parse_error_preserves_original_line_numbers():
    src = """
const FEATURE = 1;
code main:
#ifdef FEATURE
proc main() -> int {
    var x: int = ;
    return 0;
}
#else
proc main() -> int { return 1; }
#endif
"""
    with pytest.raises(SyntaxError) as exc:
        has_parser.parse(src)
    msg = str(exc.value)
    assert "Syntax error at line 6, column" in msg
    assert "var x: int = ;" in msg


def test_include_in_inactive_branch_is_not_expanded(tmp_path):
    src = """
#ifdef FEATURE
#include "missing_file.has"
#endif
const OK = 1;
"""
    mod = has_parser.parse(src, base_dir=str(tmp_path))
    assert _const_by_name(mod, "OK").value == 1


def test_include_in_active_branch_still_errors(tmp_path):
    src = """
const FEATURE = 1;
#ifdef FEATURE
#include "missing_file.has"
#endif
"""
    with pytest.raises(SyntaxError, match=r"#include: file not found"):
        has_parser.parse(src, base_dir=str(tmp_path))


@pytest.mark.parametrize(
    "op,rhs,expect_true",
    [
        ("==", "5", True),
        ("==", "6", False),
        ("=", "5", True),
        ("=", "6", False),
        ("!=", "5", False),
        ("!=", "6", True),
        ("<>", "5", False),
        ("<>", "6", True),
        (">", "4", True),
        (">", "5", False),
        ("<", "6", True),
        ("<", "5", False),
        (">=", "5", True),
        (">=", "6", False),
        ("<=", "5", True),
        ("<=", "4", False),
    ],
)
def test_if_comparison_operators_select_expected_branch(op, rhs, expect_true):
    src = f"""
const VAL = 5;
#if VAL {op} {rhs}
const X = 1;
#else
const X = 0;
#endif
"""
    mod = has_parser.parse(src)
    expected = 1 if expect_true else 0
    assert _const_by_name(mod, "X").value == expected


def test_if_with_else_selects_false_branch():
    src = """
const VAL = 3;
#if VAL == 10
const X = 1;
#else
const X = 2;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "X").value == 2


def test_if_nested_inside_ifdef():
    src = """
const FEATURE = 1;
const VAL = 7;
#ifdef FEATURE
  #if VAL > 5
  const X = 1;
  #else
  const X = 2;
  #endif
#else
const X = 3;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "X").value == 1


def test_ifdef_nested_inside_if():
    src = """
const VAL = 1;
const FEATURE = 1;
#if VAL == 1
  #ifdef FEATURE
  const X = 1;
  #else
  const X = 2;
  #endif
#else
const X = 3;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "X").value == 1


def test_if_with_arithmetic_parenthesized_rhs():
    src = """
const VAL = 5;
#if VAL >= (2+3)
const X = 1;
#else
const X = 0;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "X").value == 1


def test_if_undefined_constant_raises_syntax_error():
    src = """
#if MISSING == 1
const X = 1;
#endif
"""
    with pytest.raises(
        SyntaxError,
        match=r"undefined constant \x27MISSING\x27 used in \x27#if\x27 condition",
    ):
        has_parser.parse(src)


def test_unterminated_if_reports_preprocessor_error():
    src = """
const VAL = 1;
#if VAL == 1
const X = 1;
"""
    with pytest.raises(SyntaxError, match=r"unterminated \x27#if VAL == 1\x27 opened at line 3"):
        has_parser.parse(src)


@pytest.mark.parametrize(
    "line",
    [
        "#if VAL >= ",
        "#if VAL>=",
        "#if VAL== ",
    ],
)
def test_if_empty_rhs_reports_clear_error(line):
    src = f"""
const VAL = 5;
{line}
const X = 1;
#endif
"""
    with pytest.raises(
        SyntaxError,
        match=r"\x27#if\x27 condition for \x27VAL\x27 is missing a right-hand side expression",
    ):
        has_parser.parse(src)


def test_if_missing_operator_reports_clear_error():
    src = """
const VAL = 5;
#if VAL
const X = 1;
#endif
"""
    with pytest.raises(
        SyntaxError,
        match=r"\x27#if\x27 condition \x27VAL\x27 must be \x27IDENT OP EXPR\x27",
    ):
        has_parser.parse(src)


def test_if_undefined_constant_in_inactive_ifdef_branch_does_not_raise():
    src = """
#ifdef DISABLED
  #if UNDEFINED_CONST == 1
  const X = 1;
  #endif
#else
const X = 2;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "X").value == 2


def test_if_with_trailing_comment_parses_correctly():
    src = """
const VAL = 5;
#if VAL == 5 // comment
const X = 1;
#else
const X = 0;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "X").value == 1
