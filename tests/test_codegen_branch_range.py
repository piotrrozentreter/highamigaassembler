"""Branch displacement selection: short / word / long / 68000 trampoline."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from hasc import codegen, parser
from hasc.peepholeopt import _select_branch_sizes, peephole_optimize
from hasc.target import CpuTarget, TargetSpec


BASELINE = TargetSpec.for_cpu(CpuTarget.M68000)
TARGET_68020 = TargetSpec.for_cpu(CpuTarget.M68020)

VASM_PATH = Path(
    shutil.which("vasmm68k_mot")
    or "C:\\Users\\prozentreter\\Documents\\vbcc_win_x64\\vbcc\\bin\\vasmm68k_mot.exe"
)


def _vasm_assemble(asm_text: str, cpu: str = "68000"):
    if not VASM_PATH.exists():
        return None, "vasm not available"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".s", delete=False) as asm_file:
        asm_file.write(asm_text)
        asm_path = asm_file.name
    obj_path = asm_path.replace(".s", ".o")
    result = subprocess.run(
        [str(VASM_PATH), f"-m{cpu}", "-Fhunk", "-o", obj_path, asm_path],
        capture_output=True,
        text=True,
    )
    try:
        Path(asm_path).unlink(missing_ok=True)
        Path(obj_path).unlink(missing_ok=True)
    except OSError:
        pass
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def _pad_stmts(n: int) -> str:
    """Emit n independent stores that expand to absolute-address traffic."""
    return "\n".join(f"        g{i} = g{i} + 1;" for i in range(n))


def _pad_globals(n: int) -> str:
    return "\n".join(f"    g{i}.l = 0" for i in range(n))


def _endif_branch(asm: str) -> str | None:
    """Return the first conditional/unconditional branch targeting an endif label."""
    for line in asm.splitlines():
        m = re.match(r"\s*((?:b[a-z]+|jmp)(?:\.[swl])?)\s+(endif\d+)\b", line, re.I)
        if m:
            return line.strip()
    return None


def _bra_over_else(asm: str) -> str | None:
    for line in asm.splitlines():
        m = re.match(r"\s*(bra(?:\.[swl])?)\s+(endif\d+)\b", line, re.I)
        if m:
            return line.strip()
    return None


def test_large_conditional_body_uses_word_branch_on_68000():
    """Then-body large enough that a short beq to endif would be out of range."""
    n = 40
    src = f"""
data demo:
{_pad_globals(n)}

code main:
    proc update(x: int) -> void {{
        if (x == 0) {{
{_pad_stmts(n)}
        }}
    }}
"""
    module = parser.parse(src)
    asm = codegen.CodeGen(module, BASELINE).gen()
    branch = _endif_branch(asm)
    assert branch is not None, asm
    # Inverted false-path: bne for (== 0), beq for (!= 0), etc.
    assert re.match(r"b[a-z]{2}\.w endif\d+$", branch), branch
    assert ".s endif" not in branch

    rc, err = _vasm_assemble(asm, "68000")
    if rc is None:
        return
    assert rc == 0, err
    assert "branch destination out of range" not in err
    assert "turned into a nop" not in err


def test_large_if_else_uses_word_bra_on_68000():
    """Else body large enough that bra endif after then must not be .s."""
    n = 40
    src = f"""
data demo:
{_pad_globals(n)}

code main:
    proc update(x: int) -> int {{
        if (x == 0) {{
            return 1;
        }} else {{
{_pad_stmts(n)}
            return 0;
        }}
    }}
"""
    module = parser.parse(src)
    asm = codegen.CodeGen(module, BASELINE).gen()
    bra = _bra_over_else(asm)
    assert bra is not None, asm
    assert re.match(r"bra\.w endif\d+$", bra), bra

    # Condition still inverted-branches to else; may be short (tiny then) or word.
    assert re.search(r"\bbn[e]\.[sw]\s+else\d+\b", asm) or re.search(
        r"\bbeq\.[sw]\s+else\d+\b", asm
    ), asm

    rc, err = _vasm_assemble(asm, "68000")
    if rc is None:
        return
    assert rc == 0, err
    assert "branch destination out of range" not in err


def test_large_conditional_body_68020_stays_pc_relative():
    n = 40
    src = f"""
data demo:
{_pad_globals(n)}

code main:
    proc update(x: int) -> void {{
        if (x == 0) {{
{_pad_stmts(n)}
        }}
    }}
"""
    module = parser.parse(src)
    asm = codegen.CodeGen(module, TARGET_68020).gen()
    branch = _endif_branch(asm)
    assert branch is not None
    # Mid-size body: word (or short if estimates allow); never absolute jmp trampoline.
    assert re.match(r"b[a-z]{2}\.[sw] endif\d+$", branch), branch
    assert "jmp endif" not in asm
    assert not re.search(r"\bb[a-z]{2}\.l endif", asm)  # under long range

    rc, err = _vasm_assemble(asm, "68020")
    if rc is None:
        return
    assert rc == 0, err


def test_empty_then_drops_branch_to_following_instruction():
    """vasm warns on ble.s/beq.s to the next insn; peep should delete it."""
    lines = [
        "    ble.s endif583",
        "    ; score = VarRef(name='HIGHSCORE_MAX_VALUE')",
        "    ; assign to unknown target score",
        "endif583:",
        "    rts",
    ]
    out = _select_branch_sizes(lines, BASELINE)
    assert not any(re.search(r"\bble\.s\b", l) for l in out)
    assert any(l.strip() == "endif583:" for l in out)
    joined = "\n".join(out)
    assert "nop" not in joined  # deleted, not replaced with nop


def test_far_conditional_trampoline_on_68000_not_long_branch():
    """Past word range: inverse short + jmp, never Bcc.L on 68000."""
    pads = [f"    move.l #1,abs_sym_{i}" for i in range(6000)]
    lines = ["    beq far_target"] + pads + ["far_target:", "    rts"]
    out = _select_branch_sizes(lines, BASELINE)
    text = "\n".join(out)
    assert "beq.l" not in text
    assert "jmp far_target" in text
    assert re.search(r"bne\.s \.has_br_skip_\d+", text)
    assert ".has_br_skip_" in text

    out20 = _select_branch_sizes(lines, TARGET_68020)
    assert any(l.strip().startswith("beq.l far_target") for l in out20)


def test_control_flow_labels_preserved_for_large_if_else():
    """Semantic skeleton: false→else, then→endif, else body, endif."""
    n = 40
    src = f"""
data demo:
{_pad_globals(n)}

code main:
    proc update(x: int) -> int {{
        if (x != 0) {{
            return 1;
        }} else {{
{_pad_stmts(n)}
            return 2;
        }}
    }}
"""
    module = parser.parse(src)
    asm = codegen.CodeGen(module, BASELINE).gen()
    lines = [l.strip() for l in asm.splitlines() if l.strip()]

    # Find else/endif labels and the branches that target them.
    else_lab = next(l[:-1] for l in lines if re.match(r"else\d+:$", l))
    endif_lab = next(l[:-1] for l in lines if re.match(r"endif\d+:$", l))
    else_idx = lines.index(else_lab + ":")
    endif_idx = lines.index(endif_lab + ":")

    cond_to_else = [
        i for i, l in enumerate(lines)
        if re.search(rf"\bbeq\.[sw]\s+{re.escape(else_lab)}\b", l)
    ]
    bra_to_endif = [
        i for i, l in enumerate(lines)
        if re.search(rf"\bbra\.[sw]\s+{re.escape(endif_lab)}\b", l)
    ]
    assert cond_to_else, asm
    assert bra_to_endif, asm
    assert cond_to_else[0] < else_idx < endif_idx
    assert bra_to_endif[0] < else_idx
    then_frag = "\n".join(lines[cond_to_else[0]:else_idx])
    else_frag = "\n".join(lines[else_idx:endif_idx])
    assert re.search(r"move(?:q|\.l) #1", then_frag), then_frag
    assert re.search(r"move(?:q|\.l) #2", else_frag), else_frag


def test_peephole_optimize_still_shrinks_near_branches():
    lines = [
        "    beq.w near",
        "    moveq #1,d0",
        "near:",
        "    rts",
    ]
    out = peephole_optimize(lines, BASELINE)
    assert any("beq.s near" in line for line in out)
