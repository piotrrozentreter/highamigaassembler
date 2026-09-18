"""Focused tests for immediate-add instruction selection and call cleanup."""

import re

import pytest

from hasc import codegen as has_codegen
from hasc import parser as has_parser
from hasc import validator as has_validator
from hasc.codegen_utils import emit_add_immediate
from hasc.target import CpuTarget, TargetSpec


@pytest.mark.parametrize(
    ("reg", "expected"),
    [
        (
            "d0",
            [
                "add.l #0,d0",
                "addq.l #1,d0",
                "addq.l #8,d0",
                "add.l #9,d0",
                "add.l #32767,d0",
                "add.l #32768,d0",
            ],
        ),
        (
            "a7",
            [
                "add.l #0,a7",
                "addq.l #1,a7",
                "addq.l #8,a7",
                "lea 9(a7),a7",
                "lea 32767(a7),a7",
                "add.l #32768,a7",
            ],
        ),
    ],
)
def test_emit_add_immediate_boundaries(reg, expected):
    values = (0, 1, 8, 9, 32767, 32768)
    assert [emit_add_immediate("", reg, value) for value in values] == expected


def test_emit_add_immediate_falls_back_for_noncanonical_inputs():
    assert emit_add_immediate("", "a8", 9) == "add.l #9,a8"
    assert emit_add_immediate("", "result", 1) == "add.l #1,result"
    assert emit_add_immediate("", "a0", -1) == "add.l #-1,a0"


def _compile(src, target):
    module = has_parser.parse(src)
    val = has_validator.Validator(module)
    val.validate()
    val.apply_resolutions()
    return has_codegen.CodeGen(module, target).gen()


def _proc_body(asm, name):
    match = re.search(
        rf"(?ms)^\s*{name}:\s*$.*?(?=^\s*$\n\w+:\s*$|\Z)",
        asm,
    )
    assert match is not None
    return match.group(0)


@pytest.mark.parametrize("cpu", list(CpuTarget))
@pytest.mark.parametrize(
    ("caller_body", "return_type"),
    [
        ("return callee(1, 2, 3);", "int"),
        ("call callee(1, 2, 3);", "void"),
    ],
)
def test_three_argument_call_uses_lea_for_stack_cleanup(cpu, caller_body, return_type):
    src = f"""
code main:
    proc callee(a: int, b: int, c: int) -> int {{ return a + b + c; }}
    proc caller() -> {return_type} {{ {caller_body} }}
"""
    body = _proc_body(_compile(src, TargetSpec.for_cpu(cpu)), "caller")
    assert "jsr callee" in body
    assert "lea 12(a7),a7" in body
    assert "add.l #12,a7" not in body