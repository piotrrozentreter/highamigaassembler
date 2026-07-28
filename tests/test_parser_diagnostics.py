"""Regression tests for parser-facing developer diagnostics.

These tests validate that malformed syntax emits actionable SyntaxError text
with location, source line/caret, and targeted hints.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hasc import parser as has_parser


def test_missing_expression_after_assign_has_hint_and_caret():
    src = """
code main:
    proc main() -> int {
        var x: int = ;
        return 0;
    }
"""
    with pytest.raises(SyntaxError) as ei:
        has_parser.parse(src)
    msg = str(ei.value)
    assert "Syntax error at line 4, column" in msg
    assert "var x: int = ;" in msg
    assert "^" in msg
    assert "Hint: Missing expression after '='." in msg
    assert "CNAME" not in msg
    assert "identifier" in msg


def test_missing_section_colon_has_targeted_hint():
    src = """
code main
    proc main() -> int {
        return 0;
    }
"""
    with pytest.raises(SyntaxError) as ei:
        has_parser.parse(src)
    msg = str(ei.value)
    assert "Syntax error at line 3, column" in msg
    assert "proc main() -> int {" in msg
    assert "Hint: Did you forget ':' after section name?" in msg


def test_incomplete_comparison_has_hint():
    src = """
code main:
    proc main() -> int {
        if (1 < ) { return 1; }
        return 0;
    }
"""
    with pytest.raises(SyntaxError) as ei:
        has_parser.parse(src)
    msg = str(ei.value)
    assert "Syntax error at line 4, column" in msg
    assert "if (1 < )" in msg
    assert "Hint: Incomplete comparison expression inside parentheses." in msg


def test_missing_semicolon_has_targeted_hint():
    src = """
code main:
    proc main() -> int {
        var x: int = 1
        return x;
    }
"""
    with pytest.raises(SyntaxError) as ei:
        has_parser.parse(src)
    msg = str(ei.value)
    assert "Syntax error at line 5, column" in msg
    assert "return x;" in msg
    assert "Hint: Missing ';' at the end of the previous statement." in msg


def test_missing_closing_paren_before_block_has_hint():
    src = """
code main:
    proc main() -> int {
        if (1 < 2 { return 1; }
        return 0;
    }
"""
    with pytest.raises(SyntaxError) as ei:
        has_parser.parse(src)
    msg = str(ei.value)
    assert "Syntax error at line 4, column" in msg
    assert "if (1 < 2 {" in msg
    assert "Hint: Missing ')' before '{'." in msg
