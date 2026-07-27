"""Unit/regression tests for the Scc boolean-assignment and DBcc counter-loop
codegen fast paths described in docs/CODEGEN_SCC_DBCC_TIPS.md.

Run with:
    python -m pytest tests/test_scc_dbcc_codegen.py -v
or without pytest:
    python tests/test_scc_dbcc_codegen.py
"""

import re
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hasc import ast
from hasc import parser as has_parser
from hasc import codegen as has_codegen


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compile_src(src: str) -> str:
    """Parse + generate assembly for a HAS source string (no validation gate,
    matching `hasc.cli --no-validate`); returns the full, peephole-optimized
    assembly text."""
    mod = has_parser.parse(src)
    cg = has_codegen.CodeGen(mod)
    return cg.gen()


def proc_body(asm: str, proc_name: str) -> str:
    """Slice out just one procedure's emitted lines (from its label up to the
    next procedure), so assertions about one proc aren't confused by others or
    by internal branch labels (for1:, endfor2:, else1:, ... - which look just
    like a label but are NOT preceded by a blank line, unlike proc labels;
    see CodeGen.gen(), which always emits an empty line right before a proc's
    own label)."""
    lines = asm.splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == f"{proc_name}:")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if re.match(r'^\w+:$', stripped) and lines[i - 1].strip() == "":
            end = i - 1  # Exclude the blank separator line too
            break
    return "\n".join(lines[start:end])


def count_occurrences(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text))


def count_instruction(asm: str, mnemonic: str) -> int:
    """Count real instruction occurrences of `mnemonic`, ignoring any mention of
    the same word inside comments (e.g. "; ... dbra counter ...")."""
    count = 0
    for line in asm.splitlines():
        code = line.split(';', 1)[0].strip()
        if re.match(rf'^{re.escape(mnemonic)}\b', code):
            count += 1
    return count


def _empty_codegen() -> has_codegen.CodeGen:
    """A CodeGen instance over an empty module, for directly unit-testing the
    AST-walking helper methods without needing a full compiled program."""
    return has_codegen.CodeGen(ast.Module(items=[]))


# ---------------------------------------------------------------------------
# Scc branchless boolean assignment: if <cmp> { v = 1 } else { v = 0 }
# ---------------------------------------------------------------------------

class TestSccBoolAssign:
    def test_gt_uses_sgt_and_no_branch(self):
        src = """
code test:
    proc scc_gt(a: int, b: int) -> int {
        var flag: int = 0;
        if (a > b) {
            flag = 1;
        } else {
            flag = 0;
        }
        return flag;
    }
"""
        asm = proc_body(compile_src(src), "scc_gt")
        assert "sgt" in asm
        assert "endif" not in asm  # Fast path never allocates if/else labels
        assert "else" not in asm.lower().replace("scc_gt", "")

    def test_inverted_gt_uses_sle(self):
        """then=0/else=1 must use the *negated* comparison (sle, not sgt)."""
        src = """
code test:
    proc scc_gt_inv(a: int, b: int) -> int {
        var flag: int = 0;
        if (a > b) {
            flag = 0;
        } else {
            flag = 1;
        }
        return flag;
    }
"""
        asm = proc_body(compile_src(src), "scc_gt_inv")
        assert "sle" in asm
        assert "sgt" not in asm
        assert "endif" not in asm

    def test_eq_uses_seq(self):
        src = """
code test:
    proc scc_eq(a: int, b: int) -> int {
        var flag: int = 0;
        if (a == b) {
            flag = 1;
        } else {
            flag = 0;
        }
        return flag;
    }
"""
        asm = proc_body(compile_src(src), "scc_eq")
        assert "seq" in asm
        assert "endif" not in asm

    def test_ne_inverted_uses_seq(self):
        """not-equal, then=0/else=1 negates to == -> seq."""
        src = """
code test:
    proc scc_ne_inv(a: int, b: int) -> int {
        var flag: int = 0;
        if (a != b) {
            flag = 0;
        } else {
            flag = 1;
        }
        return flag;
    }
"""
        asm = proc_body(compile_src(src), "scc_ne_inv")
        assert "seq" in asm
        assert "endif" not in asm

    def test_unsigned_gt_uses_shi(self):
        src = """
code test:
    proc scc_unsigned(a: UWORD, b: UWORD) -> int {
        var flag: int = 0;
        if (a > b) {
            flag = 1;
        } else {
            flag = 0;
        }
        return flag;
    }
"""
        asm = proc_body(compile_src(src), "scc_unsigned")
        assert "shi" in asm
        assert "sgt" not in asm

    def test_unsigned_inverted_le_uses_sls(self):
        src = """
code test:
    proc scc_unsigned_inv(a: UWORD, b: UWORD) -> int {
        var flag: int = 0;
        if (a > b) {
            flag = 0;
        } else {
            flag = 1;
        }
        return flag;
    }
"""
        asm = proc_body(compile_src(src), "scc_unsigned_inv")
        assert "sls" in asm

    # --- Negative cases: general (branchy) path must still be used ---

    def test_different_targets_falls_back(self):
        src = """
code test:
    proc scc_diff_targets(a: int, b: int) -> int {
        var flag1: int = 0;
        var flag2: int = 0;
        if (a > b) {
            flag1 = 1;
        } else {
            flag2 = 0;
        }
        return flag1;
    }
"""
        asm = proc_body(compile_src(src), "scc_diff_targets")
        assert "endif" in asm  # General path allocates an endif label

    def test_non_bool_literals_falls_back(self):
        src = """
code test:
    proc scc_non_bool(a: int, b: int) -> int {
        var flag: int = 0;
        if (a > b) {
            flag = 2;
        } else {
            flag = 0;
        }
        return flag;
    }
"""
        asm = proc_body(compile_src(src), "scc_non_bool")
        assert "endif" in asm

    def test_multi_stmt_body_falls_back(self):
        src = """
code test:
    proc scc_multi_stmt(a: int, b: int) -> int {
        var flag: int = 0;
        var extra: int = 0;
        if (a > b) {
            flag = 1;
            extra = 1;
        } else {
            flag = 0;
        }
        return flag;
    }
"""
        asm = proc_body(compile_src(src), "scc_multi_stmt")
        assert "endif" in asm

    def test_both_branches_same_value_falls_back(self):
        src = """
code test:
    proc scc_same_value(a: int, b: int) -> int {
        var flag: int = 0;
        if (a > b) {
            flag = 1;
        } else {
            flag = 1;
        }
        return flag;
    }
"""
        asm = proc_body(compile_src(src), "scc_same_value")
        assert "endif" in asm

    def test_if_without_else_unaffected(self):
        src = """
code test:
    proc scc_no_else(a: int, b: int) -> int {
        var flag: int = 0;
        if (a > b) {
            flag = 1;
        }
        return flag;
    }
"""
        asm = proc_body(compile_src(src), "scc_no_else")
        assert "endif" in asm


# ---------------------------------------------------------------------------
# DBcc counter loop: for i = start to end [by step] { body-not-using-i }
# ---------------------------------------------------------------------------

class TestDbraForLoop:
    def test_unused_var_uses_dbra(self):
        src = """
code test:
    proc for_unused(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        for i = 0 to 9 {
            sum = sum + 1;
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "for_unused")
        assert "dbra" in asm
        assert "cmp" not in asm  # No per-iteration bound comparison remains

    def test_used_var_falls_back(self):
        src = """
code test:
    proc for_used(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        for i = 0 to 9 {
            sum = sum + i;
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "for_used")
        assert "dbra" not in asm
        assert "cmp" in asm  # General bound-check path retained

    def test_var_used_only_via_eq_comparison_falls_back(self):
        """Regression test: loops that read the counter via `==` must never
        use the dbra fast path, regardless of parser/normalization internals."""
        src = """
code test:
    proc for_used_via_eq(dummy: int) -> int {
        var result: int = 0;
        var i: int = 0;
        for i = 0 to 5 {
            if (i == 2) {
                break;
            }
            result = result + 1;
        }
        return result;
    }
"""
        asm = proc_body(compile_src(src), "for_used_via_eq")
        assert "dbra" not in asm

    def test_var_used_only_via_ne_comparison_falls_back(self):
        src = """
code test:
    proc for_used_via_ne(dummy: int) -> int {
        var result: int = 0;
        var i: int = 0;
        for i = 0 to 5 {
            if (i != 2) {
                result = result + 1;
            }
        }
        return result;
    }
"""
        asm = proc_body(compile_src(src), "for_used_via_ne")
        assert "dbra" not in asm

    def test_var_used_only_via_lt_comparison_falls_back(self):
        src = """
code test:
    proc for_used_via_lt(dummy: int) -> int {
        var result: int = 0;
        var i: int = 0;
        for i = 0 to 5 {
            if (i < 2) {
                result = result + 1;
            }
        }
        return result;
    }
"""
        asm = proc_body(compile_src(src), "for_used_via_lt")
        assert "dbra" not in asm

    def test_var_used_only_in_asm_block_falls_back(self):
        src = """
code test:
    proc for_asm_ref(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        for i = 0 to 9 {
            asm {
                move.l @i,d0
            }
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "for_asm_ref")
        assert "dbra" not in asm

    def test_custom_step_and_nonzero_start(self):
        """for i = 10 to 0 by -2 (unused): 6 iterations (10,8,6,4,2,0) -> counter=5."""
        src = """
code test:
    proc for_step(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        for i = 10 to 0 by -2 {
            sum = sum + 1;
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "for_step")
        assert "dbra" in asm
        assert re.search(r"(moveq\s+#5,d7|move\.l\s+#5,d7)", asm)

    def test_zero_iterations_falls_back(self):
        """Ascending declared (default step +1) but end < start -> 0 iterations;
        must match the general path's existing (pre-optimization) behavior."""
        src = """
code test:
    proc for_zero_iters(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        for i = 5 to 2 {
            sum = sum + 1;
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "for_zero_iters")
        assert "dbra" not in asm

    def test_dynamic_step_emits_runtime_direction_checks(self):
        src = """
code test:
    proc for_dynamic_step(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        var step: int = -1;
        for i = 3 to 0 by step {
            sum = sum + i;
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "for_dynamic_step")
        assert "dbra" not in asm
        assert "cmp.l #0,d2" in asm
        assert re.search(r"\bbeq\s+endfor\d+\b", asm)
        assert re.search(r"\bblt\s+endfor\d+_desc\b", asm)
        assert re.search(r"\bbgt\s+endfor\d+\b", asm)
        assert re.search(r"\bblt\s+endfor\d+\b", asm)

    def test_dynamic_step_uses_d2_for_increment(self):
        src = """
code test:
    proc for_dynamic_step_add(dummy: int) -> int {
        var i: int = 0;
        var step: int = 2;
        for i = 0 to 4 by step {
            i = i + 1;
        }
        return i;
    }
"""
        asm = proc_body(compile_src(src), "for_dynamic_step_add")
        assert "add.l d2,d0" in asm

    def test_boundary_65536_iterations_uses_dbra(self):
        """for i = 0 to 65535 (unused): exactly 65536 iterations, the DBcc limit."""
        src = """
code test:
    proc for_boundary_ok(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        for i = 0 to 65535 {
            sum = sum + 1;
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "for_boundary_ok")
        assert "dbra" in asm
        assert "65535" in asm  # Counter register loaded with count-1

    def test_boundary_65537_iterations_falls_back(self):
        """for i = 0 to 65536 (unused): 65537 iterations, one past the DBcc limit."""
        src = """
code test:
    proc for_boundary_over(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        for i = 0 to 65536 {
            sum = sum + 1;
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "for_boundary_over")
        assert "dbra" not in asm

    def test_empty_body_delay_loop_uses_dbra(self):
        src = """
code test:
    proc delay_loop(dummy: int) -> int {
        var i: int = 0;
        for i = 0 to 999 {
        }
        return 0;
    }
"""
        asm = proc_body(compile_src(src), "delay_loop")
        assert "dbra" in asm


# ---------------------------------------------------------------------------
# d7 nesting safety: RepeatLoop and the ForLoop fast path share one register
# ---------------------------------------------------------------------------

class TestDbraNesting:
    SAVE_RE = re.compile(r"move\.l\s+d7,-\(a7\)")
    RESTORE_RE = re.compile(r"move\.l\s+\(a7\)\+,d7")

    def test_standalone_repeat_has_no_save_restore(self):
        src = """
code test:
    proc plain_repeat(dummy: int) -> int {
        var sum: int = 0;
        repeat 5 {
            sum = sum + 1;
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "plain_repeat")
        assert count_instruction(asm, "dbra") == 1
        assert not self.SAVE_RE.search(asm)
        assert not self.RESTORE_RE.search(asm)

    def test_nested_for_in_for_saves_and_restores_d7(self):
        src = """
code test:
    proc nested_for(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        var j: int = 0;
        for i = 0 to 3 {
            for j = 0 to 4 {
                sum = sum + 1;
            }
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "nested_for")
        assert count_instruction(asm, "dbra") == 2
        assert len(self.SAVE_RE.findall(asm)) == 1
        assert len(self.RESTORE_RE.findall(asm)) == 1

    def test_repeat_nested_in_for_saves_and_restores_d7(self):
        src = """
code test:
    proc nested_repeat_in_for(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        for i = 0 to 2 {
            repeat 3 {
                sum = sum + 1;
            }
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "nested_repeat_in_for")
        assert count_instruction(asm, "dbra") == 2
        assert len(self.SAVE_RE.findall(asm)) == 1
        assert len(self.RESTORE_RE.findall(asm)) == 1

    def test_for_nested_in_repeat_saves_and_restores_d7(self):
        src = """
code test:
    proc for_in_repeat(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        repeat 3 {
            for i = 0 to 2 {
                sum = sum + 1;
            }
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "for_in_repeat")
        assert count_instruction(asm, "dbra") == 2
        assert len(self.SAVE_RE.findall(asm)) == 1
        assert len(self.RESTORE_RE.findall(asm)) == 1

    def test_triple_nested_for_saves_twice(self):
        src = """
code test:
    proc triple_nested(dummy: int) -> int {
        var sum: int = 0;
        var i: int = 0;
        var j: int = 0;
        var k: int = 0;
        for i = 0 to 1 {
            for j = 0 to 1 {
                for k = 0 to 1 {
                    sum = sum + 1;
                }
            }
        }
        return sum;
    }
"""
        asm = proc_body(compile_src(src), "triple_nested")
        assert count_instruction(asm, "dbra") == 3
        assert len(self.SAVE_RE.findall(asm)) == 2
        assert len(self.RESTORE_RE.findall(asm)) == 2

    def test_dbra_depth_resets_between_procs(self):
        """A dbra loop in one proc must not be considered 'nested' just because
        an earlier, unrelated proc also used one (dbra_depth must reset per-proc)."""
        src = """
code test:
    proc first_repeat(dummy: int) -> int {
        var sum: int = 0;
        repeat 5 {
            sum = sum + 1;
        }
        return sum;
    }

    proc second_repeat(dummy: int) -> int {
        var sum: int = 0;
        repeat 7 {
            sum = sum + 1;
        }
        return sum;
    }
"""
        asm = compile_src(src)
        first = proc_body(asm, "first_repeat")
        second = proc_body(asm, "second_repeat")
        assert not self.SAVE_RE.search(first)
        assert not self.SAVE_RE.search(second)


# ---------------------------------------------------------------------------
# Direct unit tests for the AST-walking eligibility helper
# ---------------------------------------------------------------------------

class TestForBodyBlocksDbraUnit:
    def test_varref_read_blocks(self):
        cg = _empty_codegen()
        body = [ast.ExprStmt(expr=ast.VarRef(name="i"))]
        assert cg._for_body_blocks_dbra(body, "i") is True

    def test_unrelated_varref_does_not_block(self):
        cg = _empty_codegen()
        body = [ast.ExprStmt(expr=ast.VarRef(name="j"))]
        assert cg._for_body_blocks_dbra(body, "i") is False

    def test_assign_target_write_blocks(self):
        cg = _empty_codegen()
        body = [ast.Assign(target="i", expr=ast.Number(0), is_deref=False)]
        assert cg._for_body_blocks_dbra(body, "i") is True

    def test_assign_to_other_var_does_not_block(self):
        cg = _empty_codegen()
        body = [ast.Assign(target="sum", expr=ast.Number(0), is_deref=False)]
        assert cg._for_body_blocks_dbra(body, "i") is False

    def test_asm_block_at_reference_blocks(self):
        cg = _empty_codegen()
        body = [ast.AsmBlock(content="move.l @i,d0")]
        assert cg._for_body_blocks_dbra(body, "i") is True

    def test_asm_block_unrelated_text_does_not_block(self):
        cg = _empty_codegen()
        body = [ast.AsmBlock(content="move.l @sum,d0  ; increment counter")]
        assert cg._for_body_blocks_dbra(body, "i") is False

    def test_macro_call_always_blocks(self):
        cg = _empty_codegen()
        body = [ast.MacroCall(name="do_something", args=[])]
        assert cg._for_body_blocks_dbra(body, "i") is True

    def test_nested_if_reference_blocks(self):
        cg = _empty_codegen()
        body = [
            ast.If(
                cond=ast.BinOp(op='>', left=ast.VarRef(name="i"), right=ast.Number(3)),
                then_body=[ast.Assign(target="sum", expr=ast.Number(1), is_deref=False)],
                else_body=None,
            )
        ]
        assert cg._for_body_blocks_dbra(body, "i") is True

    def test_raw_lark_tree_reference_blocks(self):
        """Regression: `==`/`!=`/`<` parse into raw, un-normalized lark.Tree nodes
        (see hasc.parser - only `>`, `<=`, `>=` get an eager BinOp transformer). The
        walker must still detect a reference buried inside such a Tree."""
        from lark import Tree
        cg = _empty_codegen()
        body = [
            ast.If(
                cond=Tree('eq', [ast.VarRef(name="i"), ast.Number(2)]),
                then_body=[ast.Break()],
                else_body=None,
            )
        ]
        assert cg._for_body_blocks_dbra(body, "i") is True

    def test_raw_lark_tree_unrelated_does_not_block(self):
        from lark import Tree
        cg = _empty_codegen()
        body = [
            ast.If(
                cond=Tree('eq', [ast.VarRef(name="j"), ast.Number(2)]),
                then_body=[ast.Break()],
                else_body=None,
            )
        ]
        assert cg._for_body_blocks_dbra(body, "i") is False

    def test_for_loop_dbra_count_basic(self):
        cg = _empty_codegen()
        stmt = ast.ForLoop(
            var="i", start=ast.Number(0), end=ast.Number(9), step=ast.Number(1),
            body=[ast.Assign(target="sum", expr=ast.Number(1), is_deref=False)],
        )
        assert cg._for_loop_dbra_count(stmt) == 10

    def test_for_loop_dbra_count_none_when_used(self):
        cg = _empty_codegen()
        stmt = ast.ForLoop(
            var="i", start=ast.Number(0), end=ast.Number(9), step=ast.Number(1),
            body=[ast.ExprStmt(expr=ast.VarRef(name="i"))],
        )
        assert cg._for_loop_dbra_count(stmt) is None

    def test_for_loop_dbra_count_descending(self):
        cg = _empty_codegen()
        stmt = ast.ForLoop(
            var="i", start=ast.Number(10), end=ast.Number(0), step=ast.Number(-2),
            body=[],
        )
        assert cg._for_loop_dbra_count(stmt) == 6


# ---------------------------------------------------------------------------
# Manual test runner (when not using pytest)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    test_classes = [
        TestSccBoolAssign,
        TestDbraForLoop,
        TestDbraNesting,
        TestForBodyBlocksDbraUnit,
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
