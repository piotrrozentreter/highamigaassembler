"""Source-contract tests for vasm optimization flags in build scripts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEVPAC_BUILD_SCRIPTS = (
    "build_example.sh",
    "build_game.sh",
    "build_msgbox_demo.sh",
    "build_snake.sh",
    "build_fileio_demo.sh",
)


def test_all_devpac_build_paths_enable_branch_relaxation() -> None:
    devpac_lines = []
    for script_name in DEVPAC_BUILD_SCRIPTS:
        script = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        devpac_lines.extend(line for line in script.splitlines() if "-devpac" in line)

    assert len(devpac_lines) == 8
    assert all("-devpac -opt-allbra" in line for line in devpac_lines)
    assert all("-opt-o1" not in line for line in devpac_lines)


def test_heap_override_preserves_branch_relaxation() -> None:
    script = (ROOT / "scripts" / "build_game.sh").read_text(encoding="utf-8")
    assert "heap_flags=(-Fhunk -devpac -opt-allbra -I" in script