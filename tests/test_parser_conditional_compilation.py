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


def test_ifdef_false_when_const_not_one():
    src = """
const FEATURE = 2;
#ifdef FEATURE
const X = 10;
#else
const X = 20;
#endif
"""
    mod = has_parser.parse(src)
    assert _const_by_name(mod, "X").value == 20


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
    assert _const_by_name(mod, "SEL").value == 12


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
    with pytest.raises(SyntaxError, match=r"Preprocessor error at line 2: '#else' without matching"):
        has_parser.parse("\n#else\nconst X = 1;\n")


def test_endif_without_if_reports_preprocessor_error():
    with pytest.raises(SyntaxError, match=r"Preprocessor error at line 2: '#endif' without matching"):
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
const FEATURE = 0;
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
