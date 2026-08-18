import subprocess
import sys
from pathlib import Path

from hasc import codegen
from hasc import parser
from hasc.target import CpuTarget, DEFAULT_TARGET, TargetSpec


ROOT = Path(__file__).resolve().parents[1]


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
    assert default_output.read_bytes() == target_68020_output.read_bytes()


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
    assert not target_68020.supports_full_index_extension
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