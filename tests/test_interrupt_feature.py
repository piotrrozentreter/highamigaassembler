"""Unit/regression tests for the `interrupt`/`starti`/`endi` VBlank dispatch-slot
feature (see docs/INTERRUPT_KEYWORD.md).

Run with:
    python -m pytest tests/test_interrupt_feature.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from hasc import parser as has_parser
from hasc import validator as has_validator
from hasc import codegen as has_codegen
from hasc.target import TargetSpec


SRC_OK = """
extern func TakeSystem() -> void;
extern func ReleaseSystem() -> void;

bss counters:
    frame_count.l: 1

code main:
    asm { jmp main }

    interrupt vbl_counter(0) -> void {
        frame_count = frame_count + 1;
    }

    proc main() -> void {
        call TakeSystem();
        starti(0);
        endi(0);
        call ReleaseSystem();
        return;
    }
"""


def _compile(src, cpu="68000"):
    mod = has_parser.parse(src)
    has_validator.Validator(mod).validate()
    cg = has_codegen.CodeGen(mod, target=TargetSpec.for_cpu(cpu))
    return cg.gen()


def test_parses_interrupt_and_starti_endi():
    mod = has_parser.parse(SRC_OK)
    cs = mod.items[-1] if hasattr(mod.items[-1], 'items') else mod.items[0]
    # Just make sure parsing doesn't raise; deeper checks happen via validate()/gen().
    assert cs is not None


def test_validator_accepts_declared_slot():
    mod = has_parser.parse(SRC_OK)
    has_validator.Validator(mod).validate()  # should not raise


def test_validator_rejects_undeclared_slot():
    src = SRC_OK.replace("starti(0);", "starti(0);\n        starti(5);")
    mod = has_parser.parse(src)
    with pytest.raises(has_validator.ValidationError, match="starti\\(5\\)"):
        has_validator.Validator(mod).validate()


def test_validator_rejects_out_of_range_index():
    src = SRC_OK.replace("interrupt vbl_counter(0)", "interrupt vbl_counter(16)")
    mod = has_parser.parse(src)
    with pytest.raises(has_validator.ValidationError, match="0-15"):
        has_validator.Validator(mod).validate()


def test_validator_rejects_duplicate_slot_index():
    src = SRC_OK + """
    interrupt vbl_counter2(0) -> void {
        return;
    }
"""
    mod = has_parser.parse(src)
    with pytest.raises(has_validator.ValidationError, match="already used"):
        has_validator.Validator(mod).validate()


def test_validator_rejects_non_void_return_in_interrupt():
    src = SRC_OK.replace(
        "interrupt vbl_counter(0) -> void {\n        frame_count = frame_count + 1;\n    }",
        "interrupt vbl_counter(0) -> void {\n        return 1;\n    }",
    )
    mod = has_parser.parse(src)
    with pytest.raises(has_validator.ValidationError, match="must always return void"):
        has_validator.Validator(mod).validate()


@pytest.mark.parametrize("cpu", ["68000", "68020"])
def test_codegen_interrupt_proc_shape(cpu):
    asm = _compile(SRC_OK, cpu=cpu)
    # Slot body: full register save/restore, ends in rts (never rte).
    idx = asm.index("vbl_counter:")
    body = asm[idx: asm.index("main:", idx)]
    assert "movem.l d0-d7/a0-a6,-(sp)" in body
    assert "movem.l (sp)+,d0-d7/a0-a6" in body
    assert body.strip().splitlines()[-1].strip() == "rts"
    assert "rte" not in body

    # Exactly one real hardware exception return (rte) in the whole file - the
    # auto-generated master VBlank ISR - never one per declared slot. Match the
    # instruction line itself (not just the substring - "started" also contains "rte").
    rte_lines = [l for l in asm.splitlines() if l.strip() == "rte"]
    assert len(rte_lines) == 1
    assert "_has_vblank_isr:" in asm
    assert "_has_int_slots:" in asm
    assert "dc.l vbl_counter" in asm


@pytest.mark.parametrize("cpu", ["68000", "68020"])
def test_codegen_starti_endi_bit_ops(cpu):
    asm = _compile(SRC_OK, cpu=cpu)
    assert "bset #0,d0" in asm
    assert "bclr #0,d0" in asm
    # Cross-section call must be jsr (absolute reloc), never bsr (PC-relative -
    # not encodable across hunk/section boundaries in the classic Amiga hunk format).
    assert "jsr _has_int_ensure_installed" in asm
    assert "bsr _has_int_ensure_installed" not in asm


def test_codegen_never_emits_68020_only_instructions():
    """The interrupt dispatch loop must stay 68000-safe (no tst.l An, which is
    a 68020-only addressing mode for TST)."""
    asm = _compile(SRC_OK, cpu="68000")
    idx = asm.index("_has_vblank_isr:")
    isr = asm[idx: asm.index("_has_int_ensure_installed:", idx)]
    assert "tst.l a0" not in isr
    assert "tst.l a1" not in isr


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
