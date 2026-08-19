from hasc.indexed_address import lower_indexed_address
from hasc import codegen, parser
from hasc.target import CpuTarget, TargetSpec


BASELINE = TargetSpec.for_cpu(CpuTarget.M68000)
TARGET_68020 = TargetSpec.for_cpu(CpuTarget.M68020)


def test_phase2_uses_68000_lowering_for_both_targets():
    expected = {
        1: ([], "(a0,d1.l)"),
        2: (["    lsl.l #1,d1"], "(a0,d1.l)"),
        4: (["    lsl.l #2,d1"], "(a0,d1.l)"),
        8: (["    lsl.l #3,d1"], "(a0,d1.l)"),
        16: (["    lsl.l #4,d1"], "(a0,d1.l)"),
    }

    for stride, result in expected.items():
        assert lower_indexed_address(BASELINE, "a0", "d1", stride) == result
        assert lower_indexed_address(TARGET_68020, "a0", "d1", stride) == result


def test_scaled_index_is_explicitly_opt_in_for_68020():
    assert lower_indexed_address(
        TARGET_68020, "a0", "d1", 4, enable_scaled=True
    ) == ([], "(a0,d1.l*4)")
    assert lower_indexed_address(
        TARGET_68020, "a0", "d1", 1, enable_scaled=True
    ) == ([], "(a0,d1.l)")


def test_scaled_index_can_include_a_displacement():
    assert lower_indexed_address(
        TARGET_68020, "a0", "d1", 4, displacement=6, enable_scaled=True
    ) == ([], "6(a0,d1.l*4)")
    assert lower_indexed_address(
        BASELINE, "a0", "d1", 4, displacement=6
    ) == (["    lsl.l #2,d1"], "6(a0,d1.l)")
    assert lower_indexed_address(
        TARGET_68020, "a0", "d1", 8, enable_scaled=True
    ) == ([], "(a0,d1.l*8)")


def test_scaled_displacement_requires_brief_index_range():
    for displacement in (-128, 127):
        lower_indexed_address(
            TARGET_68020,
            "a0",
            "d1",
            4,
            displacement=displacement,
            enable_scaled=True,
        )
    for displacement in (-129, 128):
        try:
            lower_indexed_address(
                TARGET_68020,
                "a0",
                "d1",
                4,
                displacement=displacement,
                enable_scaled=True,
            )
        except ValueError as error:
            assert "signed 8-bit" in str(error)
        else:
            raise AssertionError("out-of-range scaled displacement was accepted")


def test_arbitrary_stride_uses_existing_68000_fallbacks():
    for stride in (3, 6, 10, 12):
        prelude, operand = lower_indexed_address(BASELINE, "a0", "d1", stride)
        assert prelude == [f"    mulu.w #{stride},d1"]
        assert operand == "(a0,d1.l)"


def test_large_stride_uses_full_width_shift_add_fallback():
    prelude, operand = lower_indexed_address(BASELINE, "a0", "d1", 65536)

    assert prelude[0] == "    move.l d1,d2"
    assert prelude[1] == "    clr.l d1"
    assert "    mulu.w #65536,d1" not in prelude
    assert operand == "(a0,d1.l)"

    aliased_prelude, _ = lower_indexed_address(BASELINE, "a0", "d2", 65536)
    assert aliased_prelude[0] == "    move.l d2,d3"


def test_call_bearing_indexes_form_base_after_call():
    source = """
data values:
    values.l[4] = {10, 20, 30, 40}

code main:
    proc bump() -> int { return 1; }

    proc read() -> int {
        return values[bump()];
    }

    proc write() -> int {
        values[bump()] = 99;
        return values[1];
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert asm_68000 != asm_68020
    read_body = asm_68000[asm_68000.index("read:"):asm_68000.index("write:")]
    read_body_20 = asm_68020[asm_68020.index("read:"):asm_68020.index("write:")]
    write_body = asm_68000[asm_68000.index("write:"):]
    write_body_20 = asm_68020[asm_68020.index("write:"):]
    assert read_body.index("jsr bump") < read_body.index("lea values,a0")
    assert write_body.index("jsr bump") < write_body.index("lea values,a0")
    assert "(a0,d1.l*4)" in read_body_20
    assert "(a0,d1.l*4)" in write_body_20


def test_global_untyped_pointer_read_uses_shared_adapter():
    source = """
data test:
    ptr.l = 0

code main:
    proc bump() -> int { return 1; }

    proc read() -> int {
        return ptr[bump()];
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert asm_68000 == asm_68020
    body = asm_68000[asm_68000.index("read:"):]
    assert body.index("jsr bump") < body.index("move.l ptr,a0")
    assert "move.b (a0,d1.l),d0" in body
    assert "andi.l #$FF,d0" in body


def test_dynamic_2d_address_of_defers_base_until_calling_indexes_finish():
    source = """
data test:
    matrix.l[2][3] = {0, 1, 2, 3, 4, 5}

code main:
    proc row() -> int { return 1; }
    proc col() -> int { return 2; }

    proc address() -> int* {
        return &matrix[row()][col()];
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert asm_68000 != asm_68020
    body = asm_68000[asm_68000.index("address:"):]
    assert body.index("jsr row") < body.index("lea matrix,a0")
    assert body.index("jsr col") < body.index("lea matrix,a0")
    assert "mulu.w #3,d2" not in body
    assert "move.l d2,d3" in body
    assert "add.l d2,a0" in body
    body_20 = asm_68020[asm_68020.index("address:"):]
    assert "lea (a0,d2.l*4),a0" in body_20


def test_primitive_store_paths_use_scaled_operands_only_on_68020():
    source = """
data test:
    words.w[4] = {1, 2, 3, 4}
    longs.l[4] = {10, 20, 30, 40}

code main:
    proc update(word_index: int, long_index: int) -> int {
        words[word_index] = 7;
        longs[long_index] = 42;
        return longs[long_index];
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert "lsl.l #1,d1" in asm_68000
    assert "lsl.l #2,d1" in asm_68000
    assert "(a0,d1.l*2)" not in asm_68000
    assert "(a0,d1.l*4)" not in asm_68000
    assert "(a0,d1.l*2)" in asm_68020
    assert "(a0,d1.l*4)" in asm_68020


def test_typed_pointer_stack_parameter_uses_a6_stack_base():
    source = """
code main:
    proc read(pointer: int*, index: int) -> int {
        return pointer[index];
    }
    """
    module = parser.parse(source)
    asm = codegen.CodeGen(module, BASELINE).gen()

    assert "move.l 8(a6),a0" in asm
    assert "move.l 8(a4),a0" not in asm


def test_typed_pointer_stores_load_pointee_before_indexing():
    source = """
code main:
    proc write(pointer: int*, index: int) -> int {
        pointer[index] = 42;
        return pointer[index];
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert "move.l 8(a6),a0" in asm_68000
    assert "lea pointer,a0" not in asm_68000
    assert "(a0,d1.l)" in asm_68000
    assert "(a0,d1.l*4)" in asm_68020


def test_struct_field_displacement_scales_only_on_68020():
    source = """
bss test_bss:
    struct items[4] { value.l, tag.w, pad.w }

code main:
    proc update(index: int, value: int) -> int {
        items[index].tag = value;
        return items[index].tag;
    }
    """
    module = parser.parse(source)
    asm_68000 = codegen.CodeGen(module, BASELINE).gen()
    asm_68020 = codegen.CodeGen(module, TARGET_68020).gen()

    assert "(a0,d1.l)" in asm_68000
    assert "addq.l #4,d1" in asm_68000 or "add.l #4,d1" in asm_68000
    assert "4(a0,d1.l*8)" in asm_68020
    assert "addq.l #4,d1" not in asm_68020
    assert "add.l #4,d1" not in asm_68020
