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

    assert asm_68000 == asm_68020
    read_body = asm_68000[asm_68000.index("read:"):asm_68000.index("write:")]
    write_body = asm_68000[asm_68000.index("write:"):]
    assert read_body.index("jsr bump") < read_body.index("lea values,a0")
    assert write_body.index("jsr bump") < write_body.index("lea values,a0")
