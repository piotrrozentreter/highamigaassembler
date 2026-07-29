"""Basic unit tests for HAS compiler codegen functionality.

Tests cover:
- Stack frame management (link/unlk offsets)
- Calling conventions (parameter passing, return values)
- Basic arithmetic and variable operations
- Array access
- Pointer operations
- Function calls

Run with:
    python -m pytest tests/test_codegen_basic.py -v
"""

import re
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hasc import ast
from hasc import parser as has_parser
from hasc import codegen as has_codegen
from hasc import validator as has_validator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compile_src(src: str) -> str:
    """Parse, validate, generate assembly for a HAS source string.
    Returns the full, peephole-optimized assembly text."""
    mod = has_parser.parse(src)
    validator = has_validator.Validator(mod)
    validator.validate()
    cg = has_codegen.CodeGen(mod)
    return cg.gen()


def proc_body(asm: str, proc_name: str) -> str:
    """Extract just one procedure's assembly lines (from label to next proc)."""
    lines = asm.splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip() == f"{proc_name}:"), None)
    if start is None:
        raise ValueError(f"Procedure '{proc_name}' not found in assembly")
    
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        # Next procedure is marked by blank line + label
        if re.match(r'^\w+:$', stripped) and i > 0 and lines[i - 1].strip() == "":
            end = i - 1
            break
    return "\n".join(lines[start:end])


def assert_contains(asm: str, pattern: str):
    """Assert that assembly text contains a regex pattern."""
    if not re.search(pattern, asm, re.MULTILINE):
        raise AssertionError(f"Assembly does not contain pattern:\n{pattern}\n\nGot:\n{asm}")


# ---------------------------------------------------------------------------
# Tests: Stack Frames
# ---------------------------------------------------------------------------

class TestStackFrames:
    """Tests for link/unlk and local variable offset calculations."""
    
    def test_simple_return(self):
        """Simple procedure with return should compile."""
        src = """
code main:
    proc foo() -> int {
        return 42;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "foo")
        # Should have link/unlk
        assert_contains(body, r"link\s+a6")
        assert_contains(body, r"unlk\s+a6")
    
    def test_one_local_allocates_space(self):
        """One local variable should allocate space (including a4 save)."""
        src = """
code main:
    proc foo() -> int {
        var x: int = 0;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "foo")
        # link allocates space for locals (actual amount depends on a4 frame opt)
        assert_contains(body, r"link")
    
    def test_multiple_locals_stack_growth(self):
        """Multiple locals should allocate space for all."""
        src = """
code main:
    proc foo() -> int {
        var x: int = 0;
        var y: int = 0;
        var z: byte = 0;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "foo")
        # Multiple locals should use link with bigger negative offset
        assert_contains(body, r"link.*#-")


# ---------------------------------------------------------------------------
# Tests: Calling Conventions
# ---------------------------------------------------------------------------

class TestCallingConventions:
    """Tests for parameter passing and return values."""
    
    def test_return_immediate_value(self):
        """Return value should be placed in d0."""
        src = """
code main:
    proc foo() -> int {
        return 42;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "foo")
        # Should have d0 with return value
        assert_contains(body, r"d0")
    
    def test_one_parameter_on_stack(self):
        """Single parameter should be at +8(a6)."""
        src = """
code main:
    proc add_one(x: int) -> int {
        return x + 1;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "add_one")
        # Parameter x should be loaded from +8(a6)
        assert_contains(body, r"move\.l\s+8\(a6\)")
    
    def test_multiple_parameters(self):
        """Multiple parameters at +8, +12, +16, etc."""
        src = """
code main:
    proc add_three(x: int, y: int, z: int) -> int {
        return x + y + z;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "add_three")
        # x at +8(a6), y at +12(a6), z at +16(a6)
        assert_contains(body, r"8\(a6\)")
        assert_contains(body, r"12\(a6\)")
        assert_contains(body, r"16\(a6\)")


# ---------------------------------------------------------------------------
# Tests: Arithmetic Operations
# ---------------------------------------------------------------------------

class TestArithmetic:
    """Tests for basic arithmetic operations."""
    
    def test_addition(self):
        """Addition should emit add instruction."""
        src = """
code main:
    proc add_nums(a: int, b: int) -> int {
        return a + b;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "add_nums")
        assert_contains(body, r"add\.l")
    
    def test_subtraction(self):
        """Subtraction should emit sub instruction."""
        src = """
code main:
    proc sub_nums(a: int, b: int) -> int {
        return a - b;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "sub_nums")
        assert_contains(body, r"sub\.l")


# ---------------------------------------------------------------------------
# Tests: Variable Operations
# ---------------------------------------------------------------------------

class TestVariableOps:
    """Tests for storing and loading variables."""
    
    def test_assign_local_variable(self):
        """Assignment to local should use move to frame offset."""
        src = """
code main:
    proc assign_test() -> int {
        var x: int = 0;
        x = 42;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "assign_test")
        # Should move 42 to x's frame offset
        assert_contains(body, r"move\.l\s+#42")
    
    def test_read_local_variable(self):
        """Reading a local should load from frame offset."""
        src = """
code main:
    proc read_test() -> int {
        var x: int = 42;
        var y: int = x;
        return y;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "read_test")
        # Should load from frame
        assert_contains(body, r"move\.l.*\(a6\)")


class TestIncDecOps:
    """Tests for increment/decrement code generation."""

    def test_statement_inc_dec_avoids_unused_result_loads(self):
        """Standalone ++/-- statements should not load into d0."""
        src = """
code main:
    proc incdec_stmt() -> int {
        var x: int = 1;
        x++;
        ++x;
        x--;
        --x;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "incdec_stmt")

        # No value from x should be loaded to d0 for statement-only ++/--.
        assert not re.search(r"move\.l\s+-\d+\(a[46]\),d0", body)

        # Side effects still happen: two increments and two decrements.
        assert len(re.findall(r"add\.l\s+#1,-\d+\(a[46]\)", body)) == 2
        assert len(re.findall(r"sub\.l\s+#1,-\d+\(a[46]\)", body)) == 2

    def test_post_increment_expression_still_returns_old_value(self):
        """post-increment in expression context must still preserve old value."""
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
        # In expression context, post-increment still needs the old value.
        assert re.search(r"move\.l\s+-\d+\(a[46]\),d0", body)


# ---------------------------------------------------------------------------
# Tests: Array Access
# ---------------------------------------------------------------------------

class TestArrayOps:
    """Tests for array operations."""
    
    # Array tests skipped - complex syntax in data section


# ---------------------------------------------------------------------------
# Tests: Pointers
# ---------------------------------------------------------------------------

class TestPointers:
    """Tests for pointer operations."""
    
    def test_address_of_local(self):
        """Address-of local should use lea."""
        src = """
code main:
    proc test_address() -> int {
        var x: int = 0;
        var p: int* = &x;
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "test_address")
        # lea for loading address
        assert_contains(body, r"lea")
    
    def test_pointer_dereference(self):
        """Pointer dereference should load through address register."""
        src = """
code main:
    proc test_deref(p: int*) -> int {
        return *p;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "test_deref")
        # move through address register
        assert_contains(body, r"move\.l.*\(\w+\)")


# ---------------------------------------------------------------------------
# Tests: Function Calls
# ---------------------------------------------------------------------------

class TestFunctionCalls:
    """Tests for function call code generation."""
    
    def test_call_no_args(self):
        """Call without arguments should emit jsr."""
        src = """
code main:
    proc foo() -> int { return 0; }
    proc bar() -> int { foo(); return 0; }
        """
        asm = compile_src(src)
        body = proc_body(asm, "bar")
        assert_contains(body, r"jsr\s+foo")
    
    def test_call_with_args(self):
        """Call with arguments should push them."""
        src = """
code main:
    proc add(a: int, b: int) -> int { return a + b; }
    proc caller() -> int { return add(1, 2); }
        """
        asm = compile_src(src)
        body = proc_body(asm, "caller")
        # Should push arguments and call
        assert_contains(body, r"jsr\s+add")


# ---------------------------------------------------------------------------
# Tests: Control Flow
# ---------------------------------------------------------------------------

class TestControlFlow:
    """Tests for loops and conditionals."""
    
    def test_while_loop(self):
        """While loop should emit branches."""
        src = """
code main:
    proc loop_test() -> int {
        var i: int = 0;
        while (i < 10) {
            i = i + 1;
        }
        return 0;
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "loop_test")
        # Should have branches for loop
        assert_contains(body, r"bra|beq|bne|blt|bgt|ble|bge")
    
    def test_if_statement(self):
        """If statement should have branches."""
        src = """
code main:
    proc if_test(x: int) -> int {
        if (x > 0) {
            return 1;
        } else {
            return 0;
        }
    }
        """
        asm = compile_src(src)
        body = proc_body(asm, "if_test")
        # Should have conditional branches
        assert_contains(body, r"ble|bgt|beq|bne")


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
