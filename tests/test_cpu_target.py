import subprocess
import sys
from pathlib import Path
import re
import shutil

from hasc import codegen
from hasc import parser
from hasc.target import CpuTarget, DEFAULT_TARGET, TargetSpec


ROOT = Path(__file__).resolve().parents[1]
VASM_PATH = Path(
    shutil.which("vasmm68k_mot")
    or "C:\\Users\\prozentreter\\Documents\\vbcc_win_x64\\vbcc\\bin\\vasmm68k_mot.exe"
)


def vasm_assemble(asm_text, cpu_target="68000"):
    """Assemble with vasm for a specific CPU target.
    Returns (returncode, stdout, stderr). Skips if vasm unavailable.
    """
    import tempfile
    if not VASM_PATH.exists():
        return None, None, "vasm not available"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.s', delete=False) as asm_file:
        asm_file.write(asm_text)
        asm_path = asm_file.name

    obj_path = asm_path.replace('.s', '.o')

    result = subprocess.run(
        [str(VASM_PATH), f"-m{cpu_target}", "-Fhunkexe", "-o", obj_path, asm_path],
        capture_output=True,
        text=True,
    )

    # Clean up temp files
    try:
        Path(asm_path).unlink()
        Path(obj_path).unlink(missing_ok=True)
    except:
        pass

    return result.returncode, result.stdout, result.stderr


def test_cli_default_and_explicit_68000_outputs_are_identical(tmp_path):
    source = ROOT / "examples" / "add.has"
    default_output = tmp_path / "default.s"
    explicit_output = tmp_path / "explicit.s"
    target_68020_output = tmp_path / "target_68020.s"

    for output, cpu_args in (
        (default_output, []),
        (explicit_output, ["--cpu", "68000"]),
        (target_68020_output, ["--cpu", "68020"]),
    ):
        result = subprocess.run(
            [sys.executable, "-m", "hasc.cli", str(source), "-o", str(output), *cpu_args],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    assert default_output.read_bytes() == explicit_output.read_bytes()
    assert target_68020_output.read_bytes() == default_output.read_bytes()


def test_codegen_module_api_defaults_to_68000():
    module = parser.parse("code main:\n    proc value() -> int { return 1; }\n")

    compiler = codegen.CodeGen(module)

    assert compiler.target is DEFAULT_TARGET
    assert compiler.target.cpu is CpuTarget.M68000
    assert compiler.gen() == codegen.CodeGen(
        module, TargetSpec.for_cpu(CpuTarget.M68000)
    ).gen()


def test_target_spec_is_conservative_for_both_supported_cpus():
    baseline = TargetSpec.for_cpu(CpuTarget.M68000)
    target_68020 = TargetSpec.for_cpu(CpuTarget.M68020)

    assert not baseline.supports_scaled_index
    assert not baseline.supports_full_index_extension
    assert not baseline.supports_memory_indirect
    assert target_68020.supports_scaled_index
    assert target_68020.supports_full_index_extension
    assert not target_68020.supports_memory_indirect


def test_cli_rejects_unknown_cpu(tmp_path):
    source = ROOT / "examples" / "add.has"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hasc.cli",
            str(source),
            "-o",
            str(tmp_path / "invalid.s"),
            "--cpu",
            "68010",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "invalid choice" in result.stderr


def test_phase2_byte_array_compatibility(tmp_path):
    """Phase 0/1 gate: byte array access output is identical across CPU targets."""
    src = """
data test:
    buf.b[4] = {1, 2, 3, 4}

code main:
    proc read_byte(idx: int) -> byte {
        return buf[idx];
    }
    """
    module = parser.parse(src)
    baseline = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()
    target_68020 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()
    assert baseline == target_68020


def test_phase2_word_array_compatibility(tmp_path):
    """Phase 0/1 gate: word array access with scaling output is identical."""
    src = """
data test:
    wbuf.w[4] = {100, 200, 300, 400}

code main:
    proc read_word(idx: int) -> word {
        return wbuf[idx];
    }
    """
    module = parser.parse(src)
    baseline = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()
    target_68020 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()
    assert baseline != target_68020
    # Verify the baseline contains lsl.l #1 for word scaling
    assert "lsl.l #1" in baseline
    assert "(a0,d1.l*2)" in target_68020


def test_phase2_long_array_compatibility(tmp_path):
    """Phase 0/1 gate: long array access with 2-bit shift is identical."""
    src = """
data test:
    lbuf.l[4] = {1000, 2000, 3000, 4000}

code main:
    proc read_long(idx: int) -> int {
        return lbuf[idx];
    }
    """
    module = parser.parse(src)
    baseline = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()
    target_68020 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()
    assert baseline != target_68020
    assert "lsl.l #2" in baseline
    assert "(a0,d1.l*4)" in target_68020


def test_phase2_typed_pointer_compatibility(tmp_path):
    """Phase 0/1 gate: typed pointer indexing is identical across targets."""
    src = """
code main:
    proc read_via_ptr(ptr: int*, idx: int) -> int {
        return ptr[idx];
    }
    """
    module = parser.parse(src)
    baseline = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()
    target_68020 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()
    assert baseline != target_68020
    assert "(a0,d1.l*4)" in target_68020


def test_phase2_local_typed_pointer_read_uses_centralized_lowering():
    """Local typed-pointer reads preserve dynamic scaling and constant offsets."""
    src = """
data test:
    values.l[4] = {10, 20, 30, 40}

code main:
    proc read_local(idx: int) -> int {
        var ptr: int* = &values[0];
        return ptr[idx];
    }

    proc read_constant() -> int {
        var ptr: int* = &values[0];
        return ptr[2];
    }
    """
    module = parser.parse(src)
    baseline = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()
    target_68020 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()

    assert baseline != target_68020
    assert "lsl.l #2,d1" in baseline
    assert "move.l 8(a0),d0" in baseline
    assert "(a0,d1.l*4)" in target_68020


def test_phase2_address_of_array_element_compatibility(tmp_path):
    """Phase 0/1 gate: &array[index] is identical across targets."""
    src = """
data test:
    arr.l[10] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9}

code main:
    proc get_addr(idx: int) -> int* {
        return &arr[idx];
    }
    """
    module = parser.parse(src)
    baseline = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()
    target_68020 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()
    assert baseline != target_68020
    assert "lea (a0,d1.l),a0" in baseline
    assert "lea (a0,d1.l*4),a0" in target_68020


def test_phase2_dynamic_2d_array_compatibility():
    """Dynamic 2D reads and stores preserve the Phase 2 baseline contract."""
    src = """
data test:
    matrix.l[3][4] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}

code main:
    proc update(row: int, col: int, value: int) -> int {
        matrix[row][col] = value;
        return matrix[row][col];
    }
    """
    module = parser.parse(src)
    baseline = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()
    target_68020 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()

    assert baseline != target_68020
    assert "mulu.w #4,d2" not in baseline
    assert "move.l d2,d3" in baseline
    assert "lsl.l #2,d2" in baseline
    assert "(a0,d2.l*4)" in target_68020
    assert "lsl.l #2,d2" not in target_68020


def test_phase4_68020_emits_scaled_operands_for_long_arrays():
    """Phase 4: 68020 should emit scaled operands like (a0,d1.l*4) for long arrays."""
    src = """
data test:
    lbuf.l[4] = {1000, 2000, 3000, 4000}

code main:
    proc read_long(idx: int) -> int {
        return lbuf[idx];
    }
    """
    module = parser.parse(src)
    target_68020 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()

    assert "(a0,d1.l*4)" in target_68020
    assert "lsl.l #2,d1" not in target_68020


def test_phase4_68000_baseline_still_uses_shifts():
    """Phase 4 contract: 68000 should still emit shifts for scaling."""
    src = """
data test:
    wbuf.w[4] = {100, 200, 300, 400}

code main:
    proc read_word(idx: int) -> word {
        return wbuf[idx];
    }
    """
    module = parser.parse(src)
    baseline = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()

    # 68000 baseline: must still contain lsl.l #1 for word scaling
    assert "lsl.l #1" in baseline
    assert "(a0,d1.l*2)" not in baseline


def test_phase4_vasm_68000_assembles():
    """Phase 4: baseline output assembles with vasm -m68000."""
    if not VASM_PATH.exists():
        return  # Skip on systems without vasm

    src = """
data test:
    buf.l[4] = {1, 2, 3, 4}

code main:
    proc read(idx: int) -> int {
        return buf[idx];
    }
    """
    module = parser.parse(src)
    asm = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()

    rc, stdout, stderr = vasm_assemble(asm, "68000")
    if rc is not None:
        assert rc == 0, f"vasm -m68000 failed: {stderr}"


def test_phase4_vasm_68020_assembles():
    """Phase 4: baseline output also assembles with vasm -m68020."""
    if not VASM_PATH.exists():
        return  # Skip on systems without vasm

    src = """
data test:
    buf.l[4] = {1, 2, 3, 4}

code main:
    proc read(idx: int) -> int {
        return buf[idx];
    }
    """
    module = parser.parse(src)
    asm = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()

    rc, stdout, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_phase4_scaled_output_requires_68020_assembler():
    if not VASM_PATH.exists():
        return

    src = """
data test:
    values.l[4] = {1, 2, 3, 4}

code main:
    proc read(index: int) -> int {
        return values[index];
    }
    """
    module = parser.parse(src)
    asm = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()
    assert "(a0,d1.l*4)" in asm

    rc_20, _, stderr_20 = vasm_assemble(asm, "68020")
    assert rc_20 == 0, stderr_20
    rc_00, _, _ = vasm_assemble(asm, "68000")
    assert rc_00 != 0


def test_phase4_68020_scaled_operands_not_in_68000_output():
    """Phase 4 validation: scaled operands like *2, *4, *8 should not appear in 68000 output."""
    # This test ensures Phase 4 doesn't accidentally emit 68020 forms for 68000 target
    src = """
data test:
    wbuf.w[4] = {100, 200, 300, 400}
    lbuf.l[4] = {1000, 2000, 3000, 4000}

code main:
    proc read_word(idx: int) -> word {
        return wbuf[idx];
    }

    proc read_long(idx: int) -> int {
        return lbuf[idx];
    }
    """
    module = parser.parse(src)
    baseline = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()

    # 68000 baseline must NOT contain scaled operands
    assert re.search(r"\*[248]\s*\)", baseline) is None, "68000 output should not contain scaled operands"


def test_phase2_conversion_path1_global_1d_array_read():
    """Phase 2: Path 1 conversion - global 1D array reads use centralized helper.

    Tests that all three element sizes (byte, word, long) work correctly through
    the new centralized _lower_indexed_address helper.
    """
    src = """
data test:
    buf.l[4] = {10, 20, 30, 40}
    wbuf.w[4] = {100, 200, 300, 400}
    bbuf.b[4] = {1, 2, 3, 4}

code main:
    proc read_long(idx: int) -> int {
        return buf[idx];
    }

    proc read_word(idx: int) -> word {
        return wbuf[idx];
    }

    proc read_byte(idx: int) -> byte {
        return bbuf[idx];
    }
    """
    module = parser.parse(src)

    # The explicit 68000 output remains the compatibility baseline.
    baseline = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()
    explicit_68000 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()
    target_68020 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()
    assert baseline == explicit_68000
    assert baseline != target_68020
    assert "(a0,d1.l*4)" in target_68020

    # Verify vasm assembly succeeds for baseline
    if VASM_PATH.exists():
        rc, _, stderr = vasm_assemble(baseline, "68000")
        if rc is not None:
            assert rc == 0, f"vasm -m68000 failed on Path 1 output: {stderr}"


def test_phase4_vasm_difference_for_68020():
    """Phase 4 validation: ensure that 68020 output actually differs from 68000 when using scaled index.

    This test will verify that once Phase 2 paths are converted and Phase 4 is enabled,
    the 68020 output contains scaled operands that 68000 doesn't have.

    For now, this is a placeholder that verifies the infrastructure is in place.
    """
    if not VASM_PATH.exists():
        return  # Skip on systems without vasm

    src = """
data test:
    buf.l[10] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9}

code main:
    proc read(idx: int) -> int {
        return buf[idx];
    }
    """
    module = parser.parse(src)
    asm_68000 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()
    asm_68020 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()

    assert asm_68000 != asm_68020
    assert "(a0,d1.l*4)" not in asm_68000
    assert "(a0,d1.l*4)" in asm_68020


def test_phase1_struct_field_offset_within_brief_range_still_scales_on_68020():
    """Phase 1 non-regression: struct field offsets that already fit the
    brief range keep using scaled addressing on 68020, unscaled add on 68000.

    Note: emit_struct_array_read/emit_struct_array_store only enable scaled
    addressing when the *whole struct* fits in a 2/4/8-byte stride, so field
    offsets reachable through real struct declarations can never exceed the
    brief -128..127 range today. The full-extension relaxation for these
    wrappers is exercised directly against codegen_indexed_address in
    tests/test_codegen_68020_indexing.py using a synthetic out-of-range
    offset, since no real struct layout can trigger it yet.
    """
    src = """
bss test_bss:
    struct items[4] { value.l, tag.w, pad.w }

code main:
    proc update(index: int, value: int) -> int {
        items[index].tag = value;
        return items[index].tag;
    }
    """
    module = parser.parse(src)
    baseline = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68000)).gen()
    target_68020 = codegen.CodeGen(module, TargetSpec.for_cpu(CpuTarget.M68020)).gen()

    assert baseline != target_68020
    assert "4(a0,d1.l*8)" in target_68020

    if VASM_PATH.exists():
        rc_20, _, stderr_20 = vasm_assemble(target_68020, "68020")
        assert rc_20 == 0, f"vasm -m68020 failed: {stderr_20}"
        rc_00, _, stderr_00 = vasm_assemble(baseline, "68000")
        assert rc_00 == 0, f"vasm -m68000 failed: {stderr_00}"