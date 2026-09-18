"""High H4: validator must not mutate AST during validate(); resolutions apply after."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hasc import ast
from hasc import codegen as has_codegen
from hasc import parser as has_parser
from hasc import validator as has_validator


SRC_CONST_DIMS = """
const N = 4;
const SIZE = 8;

bss BSS:
    arr.b[N]
    buf.l: SIZE

code CODE:
    proc main() -> void {
        arr[0] = 1;
    }
"""


def _bss_globals(module):
    out = {}
    for item in module.items:
        if isinstance(item, ast.BssSection):
            for var in item.variables:
                if isinstance(var, ast.GlobalVarDecl):
                    out[var.name] = var
    return out


def test_validate_twice_without_apply_leaves_ast_unresolved():
    mod = has_parser.parse(SRC_CONST_DIMS)
    vars_ = _bss_globals(mod)
    assert vars_["arr"].dimensions == ["N"]
    assert vars_["arr"].size is None
    assert vars_["buf"].size == "SIZE"

    for _ in range(2):
        val = has_validator.Validator(mod)
        val.validate()
        assert vars_["arr"].dimensions == ["N"]
        assert vars_["arr"].size is None
        assert vars_["buf"].size == "SIZE"
        assert val.resolved_dimensions[id(vars_["arr"])] == [4]
        assert val.resolved_sizes[id(vars_["arr"])] == "4"
        assert val.resolved_sizes[id(vars_["buf"])] == "8"


def test_apply_resolutions_writes_ints_and_codegen_works():
    mod = has_parser.parse(SRC_CONST_DIMS)
    vars_ = _bss_globals(mod)
    val = has_validator.Validator(mod)
    val.validate()
    assert vars_["arr"].dimensions == ["N"]

    val.apply_resolutions()
    assert vars_["arr"].dimensions == [4]
    assert vars_["arr"].size == "4"
    assert vars_["buf"].size == "8"

    asm = has_codegen.CodeGen(mod).gen()
    assert "arr:" in asm
    assert "ds.b" in asm
