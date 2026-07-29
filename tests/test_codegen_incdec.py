"""Dedicated regression tests for ++/-- code generation.

Focus:
- Statement-form ++/-- should emit side effects without materializing unused values.
- Expression-form post-increment should preserve old-value semantics.
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hasc import codegen as has_codegen
from hasc import parser as has_parser
from hasc import validator as has_validator


def compile_src(src: str) -> str:
    mod = has_parser.parse(src)
    has_validator.Validator(mod).validate()
    return has_codegen.CodeGen(mod).gen()


def proc_body(asm: str, proc_name: str) -> str:
    lines = asm.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == f"{proc_name}:"), None)
    if start is None:
        raise ValueError(f"Procedure '{proc_name}' not found in assembly")

    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if re.match(r"^\w+:$", stripped) and i > 0 and lines[i - 1].strip() == "":
            end = i - 1
            break
    return "\n".join(lines[start:end])


class TestIncDecDedicated:
    def test_statement_local_avoids_d0_materialization(self):
        src = """
code main:
    proc local_stmt() -> int {
        var x: int = 1;
        x++;
        ++x;
        x--;
        --x;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "local_stmt")

        assert not re.search(r"move\.l\s+-\d+\(a[46]\),d0", body)
        assert len(re.findall(r"add\.l\s+#1,-\d+\(a[46]\)", body)) == 2
        assert len(re.findall(r"sub\.l\s+#1,-\d+\(a[46]\)", body)) == 2

    def test_statement_global_uses_size_suffix_without_load(self):
        src = """
data globals:
    g.l = 0
    gb.b = 0
    gw.w = 0

code main:
    proc global_stmt() -> int {
        g++;
        --g;
        gb++;
        gw--;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "global_stmt")

        assert re.search(r"add\.l\s+#1,g", body)
        assert re.search(r"sub\.l\s+#1,g", body)
        assert re.search(r"add\.b\s+#1,gb", body)
        assert re.search(r"sub\.w\s+#1,gw", body)
        assert not re.search(r"move\.[bwl]\s+g,d0", body)
        assert not re.search(r"move\.[bwl]\s+gb,d0", body)
        assert not re.search(r"move\.[bwl]\s+gw,d0", body)
        assert not re.search(r"clr\.l\s+d0", body)

    def test_statement_stack_params_use_correct_offsets(self):
        src = """
code main:
    proc stack_stmt(a: int, b: int, c: int) -> int {
        a++;
        --b;
        c--;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "stack_stmt")

        assert re.search(r"add\.l\s+#1,8\(a6\)", body)
        assert re.search(r"sub\.l\s+#1,12\(a6\)", body)
        assert re.search(r"sub\.l\s+#1,16\(a6\)", body)
        assert not re.search(r"move\.[bwl]\s+(8|12|16)\(a6\),d0", body)

    def test_statement_mixed_params_keep_stack_indexing(self):
        src = """
code main:
    proc mixed_stmt(__reg(d0) fast: int, slow1: int, slow2: int) -> int {
        fast++;
        slow1++;
        slow2--;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "mixed_stmt")

        assert re.search(r"add\.l\s+#1,-\d+\(a[46]\)", body)
        assert re.search(r"add\.l\s+#1,8\(a6\)", body)
        assert re.search(r"sub\.l\s+#1,12\(a6\)", body)

    def test_statement_areg_param_updates_register_directly(self):
        src = """
code main:
    proc areg_stmt(__reg(a0) p: ptr) -> int {
        p++;
        --p;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "areg_stmt")

        assert re.search(r"add\.l\s+#1,a0", body)
        assert re.search(r"sub\.l\s+#1,a0", body)
        assert not re.search(r"move\.l\s+a0,d0", body)

    def test_post_increment_expression_preserves_old_value(self):
        src = """
code main:
    proc post_expr() -> int {
        var x: int = 7;
        var y: int = x++;
        return y;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "post_expr")

        load_match = re.search(r"move\.l\s+-\d+\(a[46]\),d0", body)
        add_match = re.search(r"add\.l\s+#1,-\d+\(a[46]\)", body)
        assert load_match is not None
        assert add_match is not None
        assert load_match.start() < add_match.start()
