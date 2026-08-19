"""Unit tests for hasc.peepholeopt – new optimizer passes.

Run with:
    python -m pytest tests/test_peepholeopt.py -v
or without pytest:
    python tests/test_peepholeopt.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hasc.peepholeopt import (
    peephole_optimize,
    _eliminate_redundant_flag_test,
    _fold_clr_to_memory,
    _fold_neg_one,
    _eliminate_tst_after_andi_neg,
    _extract_modified_regs,
    _extract_used_regs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asm(*lines):
    """Build an assembly snippet as a list of indented lines."""
    return ["    " + l for l in lines]


def test_scaled_index_operands_preserve_register_analysis():
    assert _extract_used_regs("(a0,d1.l*4)") == {"a0", "d1"}
    assert _extract_used_regs("6(a0,d1.l*4)") == {"a0", "d1"}
    assert _extract_modified_regs("move.l (a0,d1.l*4),d0") == {"d0"}


def _join(lines):
    """Collapse a list of lines to a single string for easy comparison."""
    return "\n".join(l.rstrip() for l in lines)


# ---------------------------------------------------------------------------
# _eliminate_redundant_flag_test
# ---------------------------------------------------------------------------

class TestEliminateRedundantFlagTest:
    """Remove tst.l dN / cmp.l #0,dN when preceded by a V=0 long-word setter."""

    # --- move.l writes dN (load) ---

    def test_move_l_load_then_tst_l(self):
        inp = _asm("move.l -4(a4),d0", "tst.l d0", "beq endif1")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l" not in _join(out)
        assert "move.l -4(a4),d0" in _join(out)
        assert "beq endif1" in _join(out)

    def test_move_l_load_then_cmp_l_zero(self):
        inp = _asm("move.l -4(a4),d0", "cmp.l #0,d0", "blt loop1")
        out = _eliminate_redundant_flag_test(inp)
        assert "cmp.l" not in _join(out)
        assert "move.l -4(a4),d0" in _join(out)
        assert "blt loop1" in _join(out)

    # --- move.l reads dN (store) ---

    def test_move_l_store_then_cmp_l_zero(self):
        """move.l d0,<mem>; cmp.l #0,d0 – CCR from move still reflects d0."""
        inp = _asm("move.l d0,-4(a4)", "cmp.l #0,d0", "bge endif21")
        out = _eliminate_redundant_flag_test(inp)
        assert "cmp.l" not in _join(out)
        assert "move.l d0,-4(a4)" in _join(out)

    def test_move_l_store_then_tst_l(self):
        inp = _asm("move.l d0,-4(a4)", "tst.l d0", "beq endif")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l" not in _join(out)

    # --- moveq ---

    def test_moveq_then_tst_l(self):
        inp = _asm("moveq #-1,d1", "tst.l d1", "beq lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l" not in _join(out)

    # --- andi.l ---

    def test_andi_l_then_tst_l(self):
        inp = _asm("andi.l #$FF,d0", "tst.l d0", "beq lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l" not in _join(out)

    def test_andi_l_then_cmp_l_zero(self):
        inp = _asm("andi.l #$FF,d0", "cmp.l #0,d0", "bne lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "cmp.l" not in _join(out)

    # --- not.l, ext.l, clr.l ---

    def test_not_l_then_cmp_l_zero(self):
        inp = _asm("not.l d0", "cmp.l #0,d0", "beq lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "cmp.l" not in _join(out)

    def test_ext_l_then_tst_l(self):
        inp = _asm("ext.l d0", "tst.l d0", "bne lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l" not in _join(out)

    def test_clr_l_then_tst_l(self):
        inp = _asm("clr.l d0", "tst.l d0", "beq lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l" not in _join(out)

    # --- Safety: must NOT remove when preceding is byte/word operation ---

    def test_no_remove_after_neg_b(self):
        """neg.b is byte-only – upper bits unknown, tst.l must stay."""
        inp = _asm("neg.b d0", "tst.l d0", "beq lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l d0" in _join(out)

    def test_no_remove_after_move_b(self):
        """move.b does not clear upper bits, tst.l must stay."""
        inp = _asm("move.b -6(a4),d0", "tst.l d0", "beq lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l d0" in _join(out)

    def test_no_remove_after_move_w(self):
        """move.w does not clear upper 16 bits."""
        inp = _asm("move.w -6(a4),d0", "tst.l d0", "beq lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l d0" in _join(out)

    def test_no_remove_when_no_preceding_setter(self):
        """tst.l at beginning of block must stay."""
        inp = _asm("tst.l d0", "beq lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l d0" in _join(out)

    def test_no_remove_different_register(self):
        """move.l -4(a4),d0 followed by tst.l d1 – different registers."""
        inp = _asm("move.l -4(a4),d0", "tst.l d1", "beq lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l d1" in _join(out)

    # --- Inline comments must not break matching ---

    def test_inline_comment_on_setter(self):
        inp = ["    move.l -4(a4),d0  ; load var\n", "    tst.l d0\n", "    beq lbl\n"]
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l" not in _join(out)

    def test_inline_comment_on_tst(self):
        inp = ["    move.l -4(a4),d0\n", "    tst.l d0  ; check\n", "    beq lbl\n"]
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l" not in _join(out)

    # --- or.l / eor.l ---

    def test_or_l_then_tst_l(self):
        inp = _asm("or.l d1,d0", "tst.l d0", "bne lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l" not in _join(out)

    def test_eor_l_then_tst_l(self):
        inp = _asm("eor.l d1,d0", "tst.l d0", "bne lbl")
        out = _eliminate_redundant_flag_test(inp)
        assert "tst.l" not in _join(out)


# ---------------------------------------------------------------------------
# _fold_neg_one
# ---------------------------------------------------------------------------

class TestFoldNegOne:
    """Fold moveq #N, dX; neg.l dX  →  moveq #-N, dX."""

    def test_fold_moveq_1_neg_l(self):
        inp = _asm("moveq #1,d1", "neg.l d1")
        out = _fold_neg_one(inp)
        assert len(out) == 1
        assert "moveq #-1,d1" in _join(out)

    def test_fold_moveq_10_neg_l(self):
        inp = _asm("moveq #10,d0", "neg.l d0")
        out = _fold_neg_one(inp)
        assert len(out) == 1
        assert "moveq #-10,d0" in _join(out)

    def test_fold_moveq_neg_10_neg_l(self):
        """Negating a negative constant gives positive."""
        inp = _asm("moveq #-10,d0", "neg.l d0")
        out = _fold_neg_one(inp)
        assert len(out) == 1
        assert "moveq #10,d0" in _join(out)

    def test_fold_moveq_127_neg_l(self):
        inp = _asm("moveq #127,d2", "neg.l d2")
        out = _fold_neg_one(inp)
        assert len(out) == 1
        assert "moveq #-127,d2" in _join(out)

    def test_fold_moveq_neg_127_neg_l(self):
        inp = _asm("moveq #-127,d2", "neg.l d2")
        out = _fold_neg_one(inp)
        assert len(out) == 1
        assert "moveq #127,d2" in _join(out)

    def test_fold_moveq_neg_128_uses_move_l(self):
        """moveq #-128; neg.l → result is 128, out of moveq range → move.l."""
        inp = _asm("moveq #-128,d0", "neg.l d0")
        out = _fold_neg_one(inp)
        assert len(out) == 1
        assert "move.l #128,d0" in _join(out)

    def test_preserve_comment(self):
        inp = ["    moveq #1,d1  ; some comment\n", "    neg.l d1\n"]
        out = _fold_neg_one(inp)
        assert len(out) == 1
        assert "moveq #-1,d1" in _join(out)
        assert "some comment" in _join(out)

    def test_no_fold_neg_w(self):
        """neg.w is not folded – only neg.l."""
        inp = _asm("moveq #1,d0", "neg.w d0")
        out = _fold_neg_one(inp)
        assert len(out) == 2

    def test_no_fold_different_register(self):
        """moveq #1,d0; neg.l d1 – different registers."""
        inp = _asm("moveq #1,d0", "neg.l d1")
        out = _fold_neg_one(inp)
        assert len(out) == 2

    def test_no_fold_non_moveq(self):
        """move.l #1,d0; neg.l d0 – not moveq."""
        inp = _asm("move.l #1,d0", "neg.l d0")
        out = _fold_neg_one(inp)
        assert len(out) == 2

    def test_fold_followed_by_cmp(self):
        """Full real-world sequence: moveq #1,d1; neg.l d1; cmp.l d1,d0."""
        inp = _asm("moveq #1,d1", "neg.l d1", "cmp.l d1,d0", "bne endif1")
        out = _fold_neg_one(inp)
        assert "moveq #-1,d1" in _join(out)
        assert "neg.l" not in _join(out)
        assert "cmp.l d1,d0" in _join(out)


# ---------------------------------------------------------------------------
# _eliminate_tst_after_andi_neg
# ---------------------------------------------------------------------------

class TestEliminateTstAfterAndiNeg:
    """Remove tst.l dN from andi.l #$FF,dN; neg.b dN; tst.l dN sequence."""

    def test_byte_mask_neg_b_tst_l(self):
        inp = _asm("andi.l #$FF,d0", "neg.b d0", "tst.l d0", "beq lbl")
        out = _eliminate_tst_after_andi_neg(inp)
        assert "tst.l" not in _join(out)
        assert "andi.l #$FF,d0" in _join(out)
        assert "neg.b d0" in _join(out)
        assert "beq lbl" in _join(out)

    def test_word_mask_neg_w_tst_l(self):
        inp = _asm("andi.l #$FFFF,d0", "neg.w d0", "tst.l d0", "bne lbl")
        out = _eliminate_tst_after_andi_neg(inp)
        assert "tst.l" not in _join(out)


# ---------------------------------------------------------------------------
# _fold_clr_to_memory
# ---------------------------------------------------------------------------

class TestFoldClrToMemory:
    """Ensure clr->memory folding stays safe with indexed addressing sources."""

    def test_does_not_fold_when_indexed_load_writes_same_register(self):
        inp = _asm(
            "clr.l d0",
            "move.b (a0,d1.l),d0",
            "move.b d0,-6(a4)",
        )
        out = _fold_clr_to_memory(inp)
        text = _join(out)
        assert "clr.l d0" in text
        assert "move.b (a0,d1.l),d0" in text
        assert "move.b d0,-6(a4)" in text
        assert "move.b #0,-6(a4)" not in text

    def test_keeps_one_gap_form_when_gap_writes_source_register(self):
        inp = _asm(
            "clr.l d0",
            "move.w (a0,d1.l),d0",
            "move.b d0,(a2)",
        )
        out = _fold_clr_to_memory(inp)
        text = _join(out)
        assert "move.b #0,(a2)" not in text
        assert "move.w (a0,d1.l),d0" in text

    def test_with_inline_comment_on_neg(self):
        inp = [
            "    andi.l #$FF,d0\n",
            "    neg.b d0  ; convert FF to 01\n",
            "    tst.l d0\n",
            "    beq lbl\n",
        ]
        out = _eliminate_tst_after_andi_neg(inp)
        assert "tst.l" not in _join(out)

    def test_no_remove_mismatched_size(self):
        """andi.l #$FF + neg.w is mismatched – do not optimize."""
        inp = _asm("andi.l #$FF,d0", "neg.w d0", "tst.l d0", "beq lbl")
        out = _eliminate_tst_after_andi_neg(inp)
        assert "tst.l d0" in _join(out)

    def test_no_remove_when_no_tst(self):
        """Pattern without tst.l – nothing to remove."""
        inp = _asm("andi.l #$FF,d0", "neg.b d0", "beq lbl")
        out = _eliminate_tst_after_andi_neg(inp)
        assert len(out) == 3

    def test_no_remove_when_andi_not_ff(self):
        """andi.l with other mask – do not optimize."""
        inp = _asm("andi.l #$F0,d0", "neg.b d0", "tst.l d0", "beq lbl")
        out = _eliminate_tst_after_andi_neg(inp)
        assert "tst.l d0" in _join(out)

    def test_different_register_not_optimized(self):
        """Pattern on d1 should still be optimized correctly."""
        inp = _asm("andi.l #$FF,d1", "neg.b d1", "tst.l d1", "beq lbl")
        out = _eliminate_tst_after_andi_neg(inp)
        assert "tst.l" not in _join(out)

    def test_different_register_mismatch(self):
        """andi on d0, tst on d1 – should NOT optimize."""
        inp = _asm("andi.l #$FF,d0", "neg.b d0", "tst.l d1", "beq lbl")
        out = _eliminate_tst_after_andi_neg(inp)
        assert "tst.l d1" in _join(out)


# ---------------------------------------------------------------------------
# Integration: peephole_optimize applies all passes
# ---------------------------------------------------------------------------

class TestPeepholeIntegration:
    """Verify that new passes are included in the full peephole_optimize pipeline."""

    def test_full_pipeline_removes_tst_after_move_l(self):
        inp = _asm("move.l -4(a4),d0", "tst.l d0", "beq endif1")
        out = peephole_optimize(inp)
        assert "tst.l" not in _join(out)

    def test_full_pipeline_removes_cmp_zero_after_store(self):
        inp = _asm("move.l d0,-4(a4)", "cmp.l #0,d0", "bge endif")
        out = peephole_optimize(inp)
        assert "cmp.l" not in _join(out)

    def test_full_pipeline_folds_neg_one(self):
        inp = _asm("moveq #1,d1", "neg.l d1", "cmp.l d1,d0", "bne lbl")
        out = peephole_optimize(inp)
        assert "moveq #-1,d1" in _join(out)
        assert "neg.l" not in _join(out)

    def test_full_pipeline_removes_tst_after_andi_neg(self):
        inp = _asm("andi.l #$FF,d0", "neg.b d0", "tst.l d0", "beq lbl")
        out = peephole_optimize(inp)
        assert "tst.l" not in _join(out)

    def test_full_pipeline_preserves_unrelated_code(self):
        """Ensure unrelated instructions are untouched."""
        inp = _asm(
            "link a6,#-8",
            "move.l a4,-8(a6)",
            "move.l a6,a4",
            "moveq #5,d0",
            "move.l d0,-4(a4)",
            "unlk a6",
            "rts",
        )
        out = peephole_optimize(inp)
        # Core instructions must survive
        assert "link a6,#-8" in _join(out)
        assert "rts" in _join(out)


# ---------------------------------------------------------------------------
# Manual test runner (when not using pytest)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    test_classes = [
        TestEliminateRedundantFlagTest,
        TestFoldNegOne,
        TestEliminateTstAfterAndiNeg,
        TestPeepholeIntegration,
    ]

    passed = 0
    failed = 0

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(cls) if m.startswith("test_")]
        for method in methods:
            test_name = f"{cls.__name__}.{method}"
            try:
                getattr(instance, method)()
                print(f"  PASS  {test_name}")
                passed += 1
            except Exception:
                print(f"  FAIL  {test_name}")
                traceback.print_exc()
                failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
