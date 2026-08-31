"""Frame-register selection must match the frame setup the prologue emits.

A proc with parameters but no locals never emits the ``a4`` frame setup, so any
frame reference spelled ``(a4)`` in such a proc reads an undefined register - a
store through a pointer parameter then corrupts an arbitrary address.
"""

import re

import pytest

from hasc import codegen, parser
from hasc.target import CpuTarget, TargetSpec


TARGETS = (
    TargetSpec.for_cpu(CpuTarget.M68000),
    TargetSpec.for_cpu(CpuTarget.M68020),
)

SOURCE = """
bss frames:
    struct Rec[4] { x: i16, y: i16 }

code main:
    asm {
        jsr entry
        rts
    }

    proc store_no_locals(p: Rec*, v: int) -> void { p->x = 7; }

    proc read_no_locals(p: Rec*) -> int { return p->x; }

    proc read_store_with_locals(p: Rec*) -> int {
        var t: int;
        t = p->x;
        p->x = 9;
        return t;
    }

    proc asm_param_no_locals(x: int) -> void {
        asm {
            move.l d3,@x
        }
    }

    proc entry() -> long { return 0; }
"""

PROC_ORDER = [
    "store_no_locals",
    "read_no_locals",
    "read_store_with_locals",
    "asm_param_no_locals",
    "entry",
]

A4_SETUP = "move.l a6,a4"


def _bodies(target):
    asm = codegen.CodeGen(parser.parse(SOURCE), target).gen()
    out = {}
    bounds = PROC_ORDER + [None]
    for name, nxt in zip(bounds, bounds[1:]):
        start = asm.index(f"\n{name}:")
        end = asm.index(f"\n{nxt}:") if nxt else len(asm)
        out[name] = asm[start:end]
    return out


def _frame_regs(body):
    """Address registers used as a frame base, ignoring the a4 setup itself."""
    regs = set()
    for line in body.splitlines():
        code = line.split(";")[0]
        if A4_SETUP in code or "save a4 in frame" in line or "restore a4" in line:
            continue
        regs.update(re.findall(r"\((a[3-6])\)", code))
    return regs


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc", ["store_no_locals", "read_no_locals", "asm_param_no_locals"])
def test_no_locals_procs_never_reference_a4(target, proc):
    body = _bodies(target)[proc]
    assert A4_SETUP not in body, body
    assert _frame_regs(body) <= {"a6"}, body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_store_through_pointer_param_without_locals_uses_a6(target):
    body = _bodies(target)["store_no_locals"]
    assert "move.l 8(a6),a0" in body, body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_read_and_store_agree_without_locals(target):
    bodies = _bodies(target)
    load = "move.l 8(a6),a0"
    assert load in bodies["read_no_locals"], bodies["read_no_locals"]
    assert load in bodies["store_no_locals"], bodies["store_no_locals"]


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_locals_proc_initialises_a4_before_using_it(target):
    body = _bodies(target)["read_store_with_locals"]
    lines = [ln.strip() for ln in body.splitlines()]
    setup = next(i for i, ln in enumerate(lines) if ln.startswith(A4_SETUP))
    for i, ln in enumerate(lines[:setup]):
        assert "(a4)" not in ln.split(";")[0], body
    # Read and store of the same parameter must resolve to the same address.
    param_refs = [ln for ln in lines if re.search(r"move\.l 8\((a4|a6)\),a0", ln)]
    assert len(param_refs) == 2, body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_asm_substitution_without_locals_uses_a6(target):
    body = _bodies(target)["asm_param_no_locals"]
    assert "move.l d3,8(a6)" in body, body
