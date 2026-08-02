import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hasc import codegen as has_codegen
from hasc import parser as has_parser
from hasc import validator as has_validator


def compile_src(src: str) -> str:
    mod = has_parser.parse(src)
    validator = has_validator.Validator(mod)
    validator.validate()
    return has_codegen.CodeGen(mod).gen()


def proc_body(asm: str, proc_name: str) -> str:
    lines = asm.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == f"{proc_name}:"), None)
    if start is None:
        raise AssertionError(f"Procedure '{proc_name}' not found")

    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if re.match(r'^\w+:$', stripped) and i > 0 and lines[i - 1].strip() == "":
            end = i - 1
            break
    return "\n".join(lines[start:end])


def _assert_continue_branch_skips_tail(
    body: str,
    loop_label_prefix: str,
    tail_marker_regex: str,
    *,
    backward_target: bool = False,
):
    cont_label_match = re.search(rf"({loop_label_prefix}\d+):", body)
    if not cont_label_match:
        raise AssertionError(f"No continue label with prefix '{loop_label_prefix}' found in body:\n{body}")
    cont_label = cont_label_match.group(1)

    # Accept optional branch size suffix (e.g. bra.s) while still requiring
    # an explicit unconditional jump on the continue path.
    branch_match = re.search(rf"\bbra(?:\.[a-z]+)?\s+{re.escape(cont_label)}\b", body)
    if not branch_match:
        raise AssertionError(f"Missing explicit continue branch to '{cont_label}' in body:\n{body}")
    branch_pos = branch_match.start()

    tail_match = re.search(tail_marker_regex, body)
    if not tail_match:
        raise AssertionError(f"Tail marker regex '{tail_marker_regex}' not found in body:\n{body}")
    tail_pos = tail_match.start()

    cont_label_pos = body.find(f"{cont_label}:")
    if backward_target:
        # while-loops use loop-start as continue target, so the continue label
        # is before the guarded tail. We still require an explicit branch and
        # that it appears before tail instructions.
        assert cont_label_pos < branch_pos < tail_pos, (
            "Continue path can fall through into tail: expected backward continue branch before tail.\n"
            f"branch='bra -> {cont_label}', tail_regex='{tail_marker_regex}', label='{cont_label}:'\n{body}"
        )
    else:
        assert branch_pos < tail_pos < cont_label_pos, (
            "Continue path can fall through into tail: expected branch before tail and "
            "continue label after tail.\n"
            f"branch='bra -> {cont_label}', tail_regex='{tail_marker_regex}', label='{cont_label}:'\n{body}"
        )


def test_continue_single_level_for_early_continue():
    src = """
bss vars:
    arr.l: 8

code test:
    proc single_level() -> int {
        var i:int;
        for i = 0 to 7 {
            if (i == 3) { continue; }
            arr[i] = i;
        }
        return 0;
    }
    """
    asm = compile_src(src)
    body = proc_body(asm, "single_level")
    _assert_continue_branch_skips_tail(body, "forcont", r"\bmove\.l\s+d0,\(a0,d1\.l\)")


def test_continue_nested_if_else_for_loop():
    src = """
code test:
    proc nested_if_else() -> int {
        var i:int;
        var x:int = 0;
        for i = 0 to 7 {
            if (i < 2) {
                if (i == 1) { continue; }
                x = x + 1;
            } else {
                x = x + 2;
            }
            x = x + 10;
        }
        return x;
    }
    """
    asm = compile_src(src)
    body = proc_body(asm, "nested_if_else")
    _assert_continue_branch_skips_tail(body, "forcont", r"\badd\.l\s+#10,d0")


def test_continue_before_inline_asm_block():
    src = """
code test:
    proc continue_before_inline_asm() -> int {
        var i:int;
        var x:int = 0;
        for i = 0 to 7 {
            if (i == 0) { continue; }
            asm "move.b #1,$dff180";
            x = x + 1;
        }
        return x;
    }
    """
    asm = compile_src(src)
    body = proc_body(asm, "continue_before_inline_asm")
    _assert_continue_branch_skips_tail(body, "forcont", r"\bmove\.b\s+#1,\$dff180")


def test_continue_array_loop_with_subsequent_writes():
    src = """
bss vars:
    grid.l: 8

code test:
    proc array_loop() -> int {
        var i:int;
        for i = 0 to 7 {
            if (i == 0) { continue; }
            grid[i] = i;
            grid[0] = 123;
        }
        return 0;
    }
    """
    asm = compile_src(src)
    body = proc_body(asm, "array_loop")
    _assert_continue_branch_skips_tail(body, "forcont", r"\bmove(?:q|\.l)\s+#123,d0")


def test_continue_while_loop_skips_tail():
    src = """
code test:
    proc while_loop_continue() -> int {
        var i:int = 0;
        var sum:int = 0;
        while (i < 6) {
            i = i + 1;
            if (i == 3) { continue; }
            sum = sum + 10;
        }
        return sum;
    }
    """
    asm = compile_src(src)
    body = proc_body(asm, "while_loop_continue")
    _assert_continue_branch_skips_tail(body, "while", r"\badd(?:q)?\.l\s+#10,d0", backward_target=True)


def test_continue_do_while_loop_skips_tail():
    src = """
code test:
    proc do_while_continue() -> int {
        var i:int = 0;
        var sum:int = 0;
        do {
            i = i + 1;
            if (i == 2) { continue; }
            sum = sum + 7;
        } while (i < 5);
        return sum;
    }
    """
    asm = compile_src(src)
    body = proc_body(asm, "do_while_continue")
    _assert_continue_branch_skips_tail(body, "dowhilecont", r"\badd(?:q)?\.l\s+#7,d0")


def test_continue_repeat_loop_skips_tail():
    src = """
code test:
    proc repeat_continue() -> int {
        var i:int = 0;
        var sum:int = 0;
        repeat 5 {
            i = i + 1;
            if (i == 4) { continue; }
            sum = sum + 3;
        }
        return sum;
    }
    """
    asm = compile_src(src)
    body = proc_body(asm, "repeat_continue")
    _assert_continue_branch_skips_tail(body, "repeatcont", r"\badd(?:q)?\.l\s+#3,d0")
