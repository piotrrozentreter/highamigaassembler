"""H1/H2: typed struct pointer member R/W must not guess layouts or frame slots.

H1 — unknown pointee / unknown field must raise CodeGenError (no silent x/y/active
offsets or name-similarity struct picks).

H2 — address-register pointer params are saved like data-reg params so
``(*p).field = ...`` / ``p->field = ...`` reloads from the prologue slot after
RHS may have clobbered a0, never via ``-4 * (len(reg_params) - idx)``.
"""

import re

import pytest

from hasc import codegen, parser
from hasc.target import CpuTarget, TargetSpec


BASELINE = TargetSpec.for_cpu(CpuTarget.M68000)


def _gen(source: str) -> str:
    return codegen.CodeGen(parser.parse(source), BASELINE).gen()


def _proc_body(asm: str, name: str) -> str:
    start = asm.index(f"\n{name}:")
    # Next label at column 0, or EOF
    rest = asm[start + 1:]
    m = re.search(r"\n[A-Za-z_][A-Za-z0-9_]*:", rest)
    end = start + 1 + m.start() if m else len(asm)
    return asm[start:end]


# --- H2: a-reg pointer param store reloads saved slot -------------------------

AREG_STORE_SRC = """
bss rec_bss:
    struct Rec { x: i32, y: i32 }

code main:
    proc store_arrow(__reg(a0) p: Rec*) -> void {
        var tmp: int;
        tmp = 1;
        p->y = 42;
    }

    proc store_deref(__reg(a0) p: Rec*) -> void {
        var tmp: int;
        tmp = 1;
        (*p).x = 7;
    }

    proc entry() -> long { return 0; }
"""


def test_areg_pointer_param_saved_in_prologue():
    asm = _gen(AREG_STORE_SRC)
    body = _proc_body(asm, "store_arrow")
    assert "move.l a0,-" in body and "save p from a0" in body


def test_areg_pointer_param_arrow_store_reloads_saved_slot():
    asm = _gen(AREG_STORE_SRC)
    body = _proc_body(asm, "store_arrow")
    lines = [ln.strip() for ln in body.splitlines()]

    # Must not invent a negative offset from reg_params.index math alone
    # without a matching prologue save comment / locals slot.
    assert any(
        re.match(r"move\.l -\d+\(a[46]\),a0", ln) for ln in lines
    ), f"expected reload from saved slot, got:\n{body}"

    # Bogus pattern from old path: -4*(len-idx) with only one a-reg param
    # could emit move.l -4(a6),a0 while prologue saved elsewhere / not at all.
    # With a local `tmp`, frame has p at -4 and tmp deeper — reload must be
    # the slot that prologue wrote from a0.
    save = next(ln for ln in lines if "save p from a0" in ln)
    m = re.search(r"move\.l a0,(-\d+\(a6\))", save)
    assert m, save
    slot = m.group(1)
    assert any(ln.startswith(f"move.l {slot},a0") or ln.startswith(f"move.l {slot.replace('a6', 'a4')},a0")
               for ln in lines), f"reload must use save slot {slot}:\n{body}"

    assert "move.l #42,d0" in body or "moveq #42,d0" in body
    assert any("move.l d0,4(a0)" in ln for ln in lines)


def test_areg_pointer_param_deref_store_reloads_saved_slot():
    asm = _gen(AREG_STORE_SRC)
    body = _proc_body(asm, "store_deref")
    lines = [ln.strip() for ln in body.splitlines()]
    save = next(ln for ln in lines if "save p from a0" in ln)
    m = re.search(r"move\.l a0,(-\d+\(a6\))", save)
    assert m, save
    slot = m.group(1)
    assert any(
        ln.startswith(f"move.l {slot},a0") or ln.startswith(f"move.l {slot.replace('a6', 'a4')},a0")
        for ln in lines
    ), f"reload must use save slot {slot}:\n{body}"
    assert any(ln in ("move.l d0,(a0)", "move.l d0,0(a0)") for ln in lines)


# --- H1: no layout guessing ---------------------------------------------------

def test_unknown_pointee_member_read_fails():
    src = """
code main:
    proc bad(p: long) -> int {
        return (*p).x;
    }
"""
    with pytest.raises(codegen.CodeGenError, match="pointee struct type|Cannot resolve"):
        _gen(src)


def test_unknown_pointee_member_write_fails():
    src = """
code main:
    proc bad(p: long) -> void {
        (*p).x = 1;
    }
"""
    with pytest.raises(codegen.CodeGenError, match="pointee struct type|Cannot resolve"):
        _gen(src)


def test_unknown_field_on_typed_pointer_fails():
    src = """
bss s_bss:
    struct Rec { x: i32 }

code main:
    proc bad(__reg(a0) p: Rec*) -> int {
        return p->nope;
    }
"""
    with pytest.raises(codegen.CodeGenError, match="Unknown struct member"):
        _gen(src)


def test_name_similarity_does_not_pick_struct_layout():
    """A local named like a struct must not borrow that struct's field offsets."""
    src = """
bss s_bss:
    struct bullet { x: i32, y: i32, active: i8 }

code main:
    proc bad() -> int {
        var bullet_ptr: long;
        return (*bullet_ptr).x;
    }
"""
    with pytest.raises(codegen.CodeGenError, match="pointee struct type|Cannot resolve"):
        _gen(src)
