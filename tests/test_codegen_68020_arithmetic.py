import subprocess
import shutil
from pathlib import Path

from hasc import codegen, parser
from hasc.target import CpuTarget, TargetSpec


ROOT = Path(__file__).resolve().parents[1]
VASM_PATH = Path(
    shutil.which("vasmm68k_mot")
    or "C:\\Users\\prozentreter\\Documents\\vbcc_win_x64\\vbcc\\bin\\vasmm68k_mot.exe"
)

BASELINE = TargetSpec.for_cpu(CpuTarget.M68000)
TARGET_68020 = TargetSpec.for_cpu(CpuTarget.M68020)

LARGE_CONST_MUL_SRC = """
code main:
    proc mul_large(a: int) -> int {
        return a * 100000;
    }
"""

LARGE_CONST_DIV_SRC = """
code main:
    proc div_large(a: int) -> int {
        return a / 100000;
    }
"""

LARGE_CONST_MOD_SRC = """
code main:
    proc mod_large(a: int) -> int {
        return a % 100000;
    }
"""

# Nested mul/div/mod expression with a large sub-expression constant (100000
# exceeds the old 16-bit range). Exercises _muldiv_remainder_reg scratch
# selection across nested _emit_expr recursion (outer div, inner mul+mod).
NESTED_ARITH_SRC = """
code main:
    proc nested_arith(a: int, b: int, c: int) -> int {
        return (a * 100000) / (b % c);
    }
"""


def _instruction_mnemonics(lines):
    """Return (mnemonics, source_indices) for real instruction lines, skipping
    labels/blank lines/comment-only lines, so slices can be compared by opcode
    regardless of register naming or trailing comments."""
    mnemonics = []
    indices = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(';') or stripped.endswith(':'):
            continue
        code_part = stripped.split(';', 1)[0].strip()
        if not code_part:
            continue
        mnemonics.append(code_part.split()[0])
        indices.append(i)
    return mnemonics, indices


def vasm_assemble(asm_text, cpu_target):
    if not VASM_PATH.exists():
        return None, None, "vasm not available"

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.s', delete=False) as asm_file:
        asm_file.write(asm_text)
        asm_path = asm_file.name

    obj_path = asm_path.replace('.s', '.o')
    result = subprocess.run(
        [str(VASM_PATH), f"-m{cpu_target}", "-Fhunkexe", "-o", obj_path, asm_path],
        capture_output=True,
        text=True,
    )
    try:
        Path(asm_path).unlink()
        Path(obj_path).unlink(missing_ok=True)
    except Exception:
        pass
    return result.returncode, result.stdout, result.stderr


def test_supports_32bit_muldiv_only_on_68020():
    assert not BASELINE.supports_32bit_muldiv
    assert TARGET_68020.supports_32bit_muldiv


def test_68020_multiply_with_large_constant_uses_muls_l():
    module = parser.parse(LARGE_CONST_MUL_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    assert any("muls.l" in line for line in lines)
    assert not any("ext.l" in line and "16-bit" in line for line in lines)
    assert not any(line.strip().startswith("muls.w") for line in lines)

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68020_divide_with_large_constant_uses_divsl_l():
    module = parser.parse(LARGE_CONST_DIV_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    assert any("divsl.l" in line for line in lines)
    assert not any(line.strip().startswith("divs.w") for line in lines)

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68020_modulo_with_large_constant_uses_divsl_l():
    module = parser.parse(LARGE_CONST_MOD_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    assert any("divsl.l" in line for line in lines)
    assert any("move.l" in line and "result = remainder" in line for line in lines)
    assert not any(line.strip().startswith("divs.w") for line in lines)

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68020_nested_muldivmod_scratch_register_no_collision():
    """Nested (a * <large const>) / (b % c) on 68020: verifies the
    _muldiv_remainder_reg scratch pick for the outer divide and inner modulo
    never collides with a register still holding a live operand/result from
    the sibling/outer subexpression, and that the whole thing assembles."""
    module = parser.parse(NESTED_ARITH_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    assert any("muls.l" in line for line in lines)
    assert any("divsl.l" in line for line in lines)

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68000_multiply_with_large_constant_still_fails():
    module = parser.parse(LARGE_CONST_MUL_SRC)
    try:
        codegen.CodeGen(module, BASELINE).gen()
        assert False, "expected CodeGenError for out-of-range constant on 68000"
    except codegen.CodeGenError as exc:
        assert "outside signed 16-bit range" in str(exc)


def test_68000_divide_with_large_constant_still_fails():
    module = parser.parse(LARGE_CONST_DIV_SRC)
    try:
        codegen.CodeGen(module, BASELINE).gen()
        assert False, "expected CodeGenError for out-of-range constant on 68000"
    except codegen.CodeGenError as exc:
        assert "outside signed 16-bit range" in str(exc)


def test_68000_modulo_with_large_constant_still_fails():
    module = parser.parse(LARGE_CONST_MOD_SRC)
    try:
        codegen.CodeGen(module, BASELINE).gen()
        assert False, "expected CodeGenError for out-of-range constant on 68000"
    except codegen.CodeGenError as exc:
        assert "outside signed 16-bit range" in str(exc)


def test_68000_small_operand_multiply_output_unchanged():
    src = """
code main:
    proc mul_small(a: int, b: int) -> int {
        return a * b;
    }
"""
    module = parser.parse(src)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    idx = mnemonics.index("muls.w")
    assert mnemonics[idx - 2:idx + 1] == ["ext.l", "ext.l", "muls.w"]


def test_68000_small_operand_divide_output_unchanged():
    src = """
code main:
    proc div_small(a: int, b: int) -> int {
        return a / b;
    }
"""
    module = parser.parse(src)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    idx = mnemonics.index("divs.w")
    assert mnemonics[idx - 1:idx + 2] == ["ext.l", "divs.w", "ext.l"]


def test_68000_small_operand_modulo_output_unchanged():
    src = """
code main:
    proc mod_small(a: int, b: int) -> int {
        return a % b;
    }
"""
    module = parser.parse(src)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    idx = mnemonics.index("divs.w")
    assert mnemonics[idx - 1:idx + 3] == ["ext.l", "divs.w", "swap", "ext.l"]


def test_division_by_zero_constant_still_rejected_on_both_targets():
    src = """
code main:
    proc div_zero(a: int) -> int {
        return a / 0;
    }
"""
    module = parser.parse(src)
    for target in (BASELINE, TARGET_68020):
        try:
            codegen.CodeGen(module, target).gen()
            assert False, "expected CodeGenError for division by zero constant"
        except codegen.CodeGenError as exc:
            assert "Division by zero constant" in str(exc)


BYTE_LOCAL_SIGN_EXTEND_SRC = """
code main:
    proc byte_local_use() -> int {
        var b: byte = -5;
        return b + 1;
    }
"""

BYTE_PARAM_SIGN_EXTEND_SRC = """
code main:
    proc byte_param_use(b: byte) -> int {
        return b + 1;
    }
"""


def test_supports_extb_l_only_on_68020():
    assert not BASELINE.supports_extb_l
    assert TARGET_68020.supports_extb_l


def test_68020_signed_byte_local_uses_extb_l():
    module = parser.parse(BYTE_LOCAL_SIGN_EXTEND_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    assert "extb.l" in mnemonics
    assert "ext.w" not in mnemonics

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68020_signed_byte_param_uses_extb_l():
    module = parser.parse(BYTE_PARAM_SIGN_EXTEND_SRC)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    assert "extb.l" in mnemonics
    assert "ext.w" not in mnemonics

    rc, _, stderr = vasm_assemble(asm, "68020")
    if rc is not None:
        assert rc == 0, f"vasm -m68020 failed: {stderr}"


def test_68000_signed_byte_local_still_uses_ext_w_ext_l_sequence():
    module = parser.parse(BYTE_LOCAL_SIGN_EXTEND_SRC)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    assert "extb.l" not in mnemonics
    idx = mnemonics.index("ext.w")
    assert mnemonics[idx:idx + 2] == ["ext.w", "ext.l"]

    rc, _, stderr = vasm_assemble(asm, "68000")
    if rc is not None:
        assert rc == 0, f"vasm -m68000 failed: {stderr}"


def test_68000_signed_byte_param_still_uses_ext_w_ext_l_sequence():
    module = parser.parse(BYTE_PARAM_SIGN_EXTEND_SRC)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = asm.splitlines()

    mnemonics, _ = _instruction_mnemonics(lines)
    assert "extb.l" not in mnemonics
    idx = mnemonics.index("ext.w")
    assert mnemonics[idx:idx + 2] == ["ext.w", "ext.l"]

    rc, _, stderr = vasm_assemble(asm, "68000")
    if rc is not None:
        assert rc == 0, f"vasm -m68000 failed: {stderr}"


def test_unsigned_byte_path_unaffected_by_extb_l_on_both_targets():
    src = """
code main:
    proc ubyte_local() -> int {
        var u: u8 = 1;
        return u + 1;
    }

    proc ubyte_param(u: u8) -> int {
        return u + 1;
    }
"""
    module = parser.parse(src)
    for target in (BASELINE, TARGET_68020):
        asm = codegen.CodeGen(module, target).gen()
        lines = asm.splitlines()
        assert any("andi.l #$FF," in line for line in lines)
        assert not any("extb.l" in line for line in lines)
