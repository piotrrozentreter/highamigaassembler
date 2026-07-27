"""End-to-end HAS <-> vbcc interop smoke tests.

These tests validate object-level ABI compatibility by compiling, assembling,
and linking mixed HAS/C artifacts in both directions:

1) HAS code calls C functions compiled by vbcc.
2) C code compiled by vbcc calls HAS-exported procedures.

The goal is to prove that if both sides compile, the linker can combine them
for the currently supported scalar/pointer type surface.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


HASC_TYPES = [
    # canonical names
    ("t00_byte", "byte", "signed char"),
    ("t01_word", "word", "short"),
    ("t02_int", "int", "int"),
    ("t03_long", "long", "long"),
    ("t04_bool", "bool", "unsigned char"),
    ("t05_ptr", "ptr", "void *"),
    # aliases
    ("t06_i8", "i8", "signed char"),
    ("t07_u8", "u8", "unsigned char"),
    ("t08_char", "char", "char"),
    ("t09_i16", "i16", "short"),
    ("t10_u16", "u16", "unsigned short"),
    ("t11_short", "short", "short"),
    ("t12_i32", "i32", "int"),
    ("t13_u32", "u32", "unsigned int"),
    ("t14_ubyte", "UBYTE", "unsigned char"),
    ("t15_byte_alias", "BYTE", "signed char"),
    ("t16_uword", "UWORD", "unsigned short"),
    ("t17_word_alias", "WORD", "short"),
    ("t18_ulong", "ULONG", "unsigned long"),
    ("t19_long_alias", "LONG", "long"),
    ("t20_aptr", "APTR", "void *"),
]


def _which_or_skip(name: str) -> str:
    path = shutil.which(name)
    if not path:
        pytest.skip(f"Required tool not found on PATH: {name}")
    return path


def _prepare_env() -> dict[str, str]:
    """Prepare environment for vc/vbcc tools.

    vc usually needs VBCC set to the root installation path. If it's not set,
    infer it from vc location: <VBCC>/bin/vc.
    """
    env = os.environ.copy()
    if "VBCC" not in env or not env["VBCC"].strip():
        vc_path = Path(_which_or_skip("vc"))
        env["VBCC"] = str(vc_path.parent.parent)
    return env


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _assert_ok(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode == 0:
        return
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    pytest.fail(
        f"{label} failed with exit code {result.returncode}\n"
        f"STDOUT:\n{stdout}\n\n"
        f"STDERR:\n{stderr}"
    )


def _emit_c_type_identity_functions(prefix: str) -> str:
    lines: list[str] = []
    for key, _has_type, c_type in HASC_TYPES:
        name = f"{prefix}_{key}"
        lines.append(f"{c_type} {name}({c_type} v) {{ return v; }}")
    return "\n".join(lines) + "\n"


def _emit_has_extern_decls(prefix: str) -> str:
    lines: list[str] = []
    for key, has_type, _c_type in HASC_TYPES:
        # C symbols are underscore-prefixed in this vbcc target.
        lines.append(f"    extern func _{prefix}_{key}(v: {has_type}) -> {has_type};")
    return "\n".join(lines)


def _emit_has_calls(prefix: str) -> str:
    lines: list[str] = ["        var p: ptr = 0;", "        var acc: int = 0;"]
    for key, has_type, _c_type in HASC_TYPES:
        callee = f"_{prefix}_{key}"
        if has_type in {"ptr", "APTR"}:
            lines.append(f"        p = {callee}(p);")
            lines.append("        if (p == 0) { acc = acc + 1; } else { acc = acc + 2; }")
        else:
            lines.append(f"        acc = acc + {callee}(1);")
    lines.append("        return acc;")
    return "\n".join(lines)


def _emit_has_exports(prefix: str) -> str:
    parts: list[str] = []
    for key, has_type, _c_type in HASC_TYPES:
        base = f"{prefix}_{key}"
        parts.append(f"    public _{base};")
        parts.append(f"    proc _{base}(v: {has_type}) -> {has_type} {{")
        parts.append("        return v;")
        parts.append("    }")
        parts.append("")
    parts.append(f"    public _{prefix}_entry;")
    parts.append(f"    proc _{prefix}_entry() -> int {{")
    parts.append("        return 0;")
    parts.append("    }")
    return "\n".join(parts)


def _emit_c_calls_to_has(prefix: str) -> str:
    lines: list[str] = []
    for key, _has_type, c_type in HASC_TYPES:
        # C declaration without leading underscore maps to symbol _name in vbcc.
        lines.append(f"extern {c_type} {prefix}_{key}({c_type} v);")
    lines.append("")
    lines.append("int call_all_from_c(void) {")
    lines.append("    int acc = 0;")
    lines.append("    void *p = (void *)0;")
    for key, has_type, _c_type in HASC_TYPES:
        fn = f"{prefix}_{key}"
        if has_type in {"ptr", "APTR"}:
            lines.append(f"    p = {fn}(p);")
            lines.append("    acc += (p == 0) ? 1 : 2;")
        else:
            lines.append(f"    acc += (int){fn}(1);")
    lines.append("    return acc;")
    lines.append("}")
    return "\n".join(lines) + "\n"


def test_has_calls_c_and_links_for_supported_types(tmp_path: Path) -> None:
    _which_or_skip("vc")
    _which_or_skip("vasmm68k_mot")
    _which_or_skip("vlink")

    env = _prepare_env()
    repo_root = Path(__file__).resolve().parents[1]

    has_src = tmp_path / "has_calls_c_types.has"
    c_src = tmp_path / "c_impl_for_has.c"
    has_asm = tmp_path / "has_calls_c_types.s"
    has_obj = tmp_path / "has_calls_c_types.o"
    c_obj = tmp_path / "c_impl_for_has.o"
    linked = tmp_path / "has_calls_c_types_linked.o"

    has_src.write_text(
        "\n".join(
            [
                "code interop:",
                _emit_has_extern_decls("c_id"),
                "",
                "    public has_entry;",
                "    proc has_entry() -> int {",
                _emit_has_calls("c_id"),
                "    }",
                "",
            ]
        ),
        encoding="ascii",
    )

    c_src.write_text(_emit_c_type_identity_functions("c_id"), encoding="ascii")

    py = sys.executable
    r = _run([py, "-m", "hasc.cli", str(has_src), "-o", str(has_asm)], cwd=repo_root, env=env)
    _assert_ok(r, "Compile HAS source")

    r = _run(["vasmm68k_mot", "-Fhunk", "-o", str(has_obj), str(has_asm)], cwd=repo_root, env=env)
    _assert_ok(r, "Assemble HAS output")

    target = env.get("VBCC_TARGET", "aos68k")
    r = _run(["vc", f"+{target}", "-c", str(c_src), "-o", str(c_obj)], cwd=repo_root, env=env)
    _assert_ok(r, "Compile C source with vbcc")

    r = _run(["vlink", "-bamigahunk", "-r", str(has_obj), str(c_obj), "-o", str(linked)], cwd=repo_root, env=env)
    _assert_ok(r, "Relocatable link HAS->C objects")

    assert linked.exists(), "Expected linked object for HAS->C interop"


def test_c_calls_has_and_links_for_supported_types(tmp_path: Path) -> None:
    _which_or_skip("vc")
    _which_or_skip("vasmm68k_mot")
    _which_or_skip("vlink")

    env = _prepare_env()
    repo_root = Path(__file__).resolve().parents[1]

    has_src = tmp_path / "has_exports_types.has"
    c_src = tmp_path / "c_calls_has_types.c"
    has_asm = tmp_path / "has_exports_types.s"
    has_obj = tmp_path / "has_exports_types.o"
    c_obj = tmp_path / "c_calls_has_types.o"
    linked = tmp_path / "c_calls_has_types_linked.o"

    has_src.write_text(
        "\n".join(
            [
                "code interop:",
                _emit_has_exports("h_id"),
                "",
            ]
        ),
        encoding="ascii",
    )
    c_src.write_text(_emit_c_calls_to_has("h_id"), encoding="ascii")

    py = sys.executable
    r = _run([py, "-m", "hasc.cli", str(has_src), "-o", str(has_asm)], cwd=repo_root, env=env)
    _assert_ok(r, "Compile HAS exports")

    r = _run(["vasmm68k_mot", "-Fhunk", "-o", str(has_obj), str(has_asm)], cwd=repo_root, env=env)
    _assert_ok(r, "Assemble HAS exports")

    target = env.get("VBCC_TARGET", "aos68k")
    r = _run(["vc", f"+{target}", "-c", str(c_src), "-o", str(c_obj)], cwd=repo_root, env=env)
    _assert_ok(r, "Compile C caller with vbcc")

    r = _run(["vlink", "-bamigahunk", "-r", str(c_obj), str(has_obj), "-o", str(linked)], cwd=repo_root, env=env)
    _assert_ok(r, "Relocatable link C->HAS objects")

    assert linked.exists(), "Expected linked object for C->HAS interop"
