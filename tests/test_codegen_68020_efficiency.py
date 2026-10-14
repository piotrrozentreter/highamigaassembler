"""68020 efficiency follow-ups: long branches, stride mulu.l, long data align."""

from hasc import codegen, parser
from hasc.peepholeopt import _select_branch_sizes, peephole_optimize
from hasc.target import CpuTarget, TargetSpec


BASELINE = TargetSpec.for_cpu(CpuTarget.M68000)
TARGET_68020 = TargetSpec.for_cpu(CpuTarget.M68020)


def test_supports_long_branches_and_prefers_long_alignment_flags():
    assert not BASELINE.supports_long_branches
    assert not BASELINE.prefers_long_alignment
    assert TARGET_68020.supports_long_branches
    assert TARGET_68020.prefers_long_alignment


def test_short_branches_prefer_s_suffix_on_both_targets():
    src = """
code main:
    proc check(x: int) -> int {
        if (x == 0) {
            return 1;
        }
        return 0;
    }
"""
    module = parser.parse(src)
    for target in (BASELINE, TARGET_68020):
        asm = codegen.CodeGen(module, target).gen()
        # Condition/exit branches in this tiny proc are short.
        assert "beq.s" in asm or "bne.s" in asm
        assert "bra.l" not in asm
        assert "beq.l" not in asm


def test_select_branch_sizes_emits_bra_l_only_on_68020():
    """Synthetic span past word range -> .l on 68020, .w on 68000."""
    # 4 bytes/insn estimate: >32766 bytes needs >8192 insn lines between
    # the branch and the label (plus the branch's own size).
    nops = [f"    nop  ; pad {i}" for i in range(9000)]
    lines = ["    bra far_target"] + nops + ["far_target:", "    rts"]

    out_20 = _select_branch_sizes(lines, TARGET_68020)
    out_00 = _select_branch_sizes(lines, BASELINE)

    assert any(line.strip().startswith("bra.l far_target") for line in out_20)
    assert any(line.strip().startswith("bra.w far_target") for line in out_00)
    assert not any(".l far_target" in line for line in out_00)


def test_select_branch_sizes_shrinks_word_to_short():
    lines = [
        "    beq.w near",
        "    moveq #1,d0",
        "near:",
        "    rts",
    ]
    out = _select_branch_sizes(lines, BASELINE)
    assert out[0].strip().startswith("beq.s near")


def test_and_or_short_circuit_uses_short_branches():
    src = """
code main:
    proc both(a: int, b: int) -> int {
        return a && b;
    }
"""
    module = parser.parse(src)
    asm_00 = codegen.CodeGen(module, BASELINE).gen()
    asm_20 = codegen.CodeGen(module, TARGET_68020).gen()
    assert "beq.s" in asm_00
    assert "bra.s" in asm_00
    assert "beq.w" not in asm_00
    assert "beq.s" in asm_20
    assert "bra.l" not in asm_20


def test_long_data_alignment_cnop_only_on_68020():
    src = """
data demo:
    flag.b = 1
    value.l = 42

code main:
    proc read() -> int {
        return value;
    }
"""
    module = parser.parse(src)
    asm_00 = codegen.CodeGen(module, BASELINE).gen()
    asm_20 = codegen.CodeGen(module, TARGET_68020).gen()

    # After flag.b the running offset is odd/unaligned for a long.
    assert "value:" in asm_00
    assert "value:" in asm_20

    # Extract the data-section fragment around value.
    def _before_label(asm: str, label: str) -> str:
        lines = asm.splitlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{label}:"):
                return "\n".join(lines[max(0, i - 3):i])
        raise AssertionError(f"missing label {label}")

    before_00 = _before_label(asm_00, "value")
    before_20 = _before_label(asm_20, "value")
    assert "even" in before_00
    assert "cnop 0,4" in before_20
    # 68000 must not gain the 68020 long-align directive before this label.
    assert "cnop 0,4" not in before_00.split("flag:")[-1] if "flag:" in before_00 else "cnop 0,4" not in before_00


def test_peephole_optimize_runs_branch_sizing():
    lines = [
        "    beq.w near",
        "    nop",
        "near:",
        "    rts",
    ]
    out = peephole_optimize(lines, BASELINE)
    assert any("beq.s near" in line for line in out)
