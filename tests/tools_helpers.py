"""Shared helpers for the tools/ asset-pipeline test suite."""
import re
from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")

SECTION_RE = re.compile(r"^\s*SECTION\s+", re.IGNORECASE)
CNOP_RE = re.compile(r"^\s*CNOP\s+0\s*,\s*4\s*$", re.IGNORECASE)


def make_png(path: Path, width: int, height: int, colors=None) -> Path:
    """Write a deterministic RGBA PNG; pixel (x, y) cycles through `colors`."""
    colors = colors or [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (0, 0, 0, 0)]
    img = Image.new("RGBA", (width, height))
    img.putdata([colors[(x + y) % len(colors)] for y in range(height) for x in range(width)])
    img.save(path)
    return path


def assert_section_cnop_invariant(asm: str) -> None:
    """Every SECTION directive must be immediately followed by CNOP 0,4."""
    lines = asm.split("\n")
    section_lines = [i for i, line in enumerate(lines) if SECTION_RE.match(line)]
    assert section_lines, "expected at least one SECTION directive"
    for i in section_lines:
        assert i + 1 < len(lines), f"SECTION on last line, missing CNOP: {lines[i]!r}"
        assert CNOP_RE.match(lines[i + 1]), (
            f"SECTION not followed by 'CNOP 0,4': {lines[i]!r} -> {lines[i + 1]!r}"
        )


def data_words(asm: str, label: str):
    """Return the DC.W operand strings emitted directly under `label`."""
    lines = asm.split("\n")
    start = next(i for i, line in enumerate(lines) if line.strip() == f"{label}:")
    words = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if not stripped:
            break
        if stripped.upper().startswith("DC.W"):
            operand = stripped[4:].split(";")[0].strip()
            words.extend(part.strip() for part in operand.split(","))
        else:
            break
    return words
