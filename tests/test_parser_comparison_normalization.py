"""Parser regression tests for comparison-operator AST normalization.

These tests ensure all comparison operators are transformed into `ast.BinOp`
by ASTBuilder, instead of leaking raw parse trees into later compiler stages.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hasc import ast
from hasc import parser as has_parser


def _first_proc(module: ast.Module) -> ast.Proc:
    for item in module.items:
        if isinstance(item, ast.Proc):
            return item
        if hasattr(item, "items"):
            for child in item.items:
                if isinstance(child, ast.Proc):
                    return child
    raise AssertionError("No procedure found in parsed module")


def _if_condition_for(op: str):
    src = f"""
code test:
    proc cmp(x: int, y: int) -> int {{
        if (x {op} y) {{
            return 1;
        }}
        return 0;
    }}
"""
    mod = has_parser.parse(src)
    proc = _first_proc(mod)
    assert proc.body, "Procedure body is empty"
    assert isinstance(proc.body[0], ast.If)
    return proc.body[0].cond


def test_eq_comparison_builds_binop():
    cond = _if_condition_for("==")
    assert isinstance(cond, ast.BinOp)
    assert cond.op == "=="


def test_ne_comparison_builds_binop():
    cond = _if_condition_for("!=")
    assert isinstance(cond, ast.BinOp)
    assert cond.op == "!="


def test_lt_comparison_builds_binop():
    cond = _if_condition_for("<")
    assert isinstance(cond, ast.BinOp)
    assert cond.op == "<"


def test_all_comparison_operators_build_binop():
    for op in ["==", "!=", "<", "<=", ">", ">="]:
        cond = _if_condition_for(op)
        assert isinstance(cond, ast.BinOp), f"Expected BinOp for operator {op}"
        assert cond.op == op
