"""Repo-wide conventions for assembly emitted by tools/.

These guard invariants that are easy to break when adding a new generator or a
new SECTION emission site, and that no single tool's own tests would catch.
"""
import re
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"

# Matches an emission-site string literal like  f"\tSECTION bobs,DATA_C"  as well
# as the real-tab variant used by frame_merger.py. Docstrings and prose do not
# carry the leading tab, so they are excluded.
EMIT_SECTION_RE = re.compile(r"(?:\\t|\t)\s*SECTION\s+(\w+)\s*,\s*(\w+)")

# Chip RAM is scarce: only data the custom chips DMA from belongs in a *_C
# section. Extend this list only for genuine graphics/audio DMA data.
CHIP_SECTION_ALLOWLIST = {"bobs", "tileset", "sprites", "copperlists", "audio"}


def _tool_sources():
    return sorted(p for p in TOOLS_DIR.glob("*.py") if not p.name.startswith("_"))


def _emission_sites():
    for path in _tool_sources():
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        for i, line in enumerate(lines):
            match = EMIT_SECTION_RE.search(line)
            if match:
                yield path, i, lines, match


@pytest.mark.parametrize("path", _tool_sources(), ids=lambda p: p.name)
def test_every_section_emission_is_followed_by_cnop(path: Path):
    """A SECTION must be followed by CNOP 0,4 so the first label is 4-byte aligned."""
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    sites = [i for i, line in enumerate(lines) if EMIT_SECTION_RE.search(line)]

    for i in sites:
        window = lines[i + 1:i + 4]
        assert any("CNOP" in line for line in window), (
            f"{path.name}:{i + 1} emits a SECTION without a following CNOP 0,4:\n"
            f"  {lines[i].strip()}"
        )


def test_chip_ram_sections_are_limited_to_dma_data():
    """DATA_C/BSS_C is only for chip-DMA data (bitplanes, BOBs, sprites, copper, audio)."""
    offenders = []
    for path, i, _lines, match in _emission_sites():
        name, kind = match.group(1), match.group(2).upper()
        if kind.endswith("_C") and name not in CHIP_SECTION_ALLOWLIST:
            offenders.append(f"{path.name}:{i + 1} SECTION {name},{kind}")

    assert not offenders, (
        "Chip RAM used for a section not known to be DMA'd by the custom chips.\n"
        "Move it to plain DATA/BSS (fast RAM), or extend CHIP_SECTION_ALLOWLIST "
        "if it really is graphics/audio DMA data:\n  " + "\n  ".join(offenders)
    )


def test_sprite_templates_stay_in_fast_ram():
    """Hardware sprite templates are CPU-copied to chip RAM by CreateSprite."""
    source = (TOOLS_DIR / "sprite_importer.py").read_text(encoding="utf-8")

    assert "SECTION sprite_templates,DATA" in source
    assert "SECTION sprite_templates,DATA_C" not in source


@pytest.mark.parametrize("path", _tool_sources(), ids=lambda p: p.name)
def test_emitted_directives_are_uppercase(path: Path):
    """tools/*.py emit uppercase directives (unlike hasc/codegen.py, which is lowercase)."""
    source = path.read_text(encoding="utf-8", errors="replace")

    for lowercase in (r"\tsection ", r"\txdef", r"\tcnop", r"\tdc.w", r"\tdc.l", r"\tds.b"):
        assert lowercase not in source, f"{path.name} emits lowercase directive {lowercase!r}"


def test_getdata_is_not_called_directly():
    """Pillow 14 removes Image.getdata; tools must go through flatten_image_pixels."""
    offenders = []
    for path in _tool_sources():
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").split("\n")):
            if ".getdata()" in line and "def flatten_image_pixels" not in line:
                # The compat helper itself is the one allowed caller.
                if "hasattr(img, 'get_flattened_data')" in line:
                    continue
                offenders.append((path.name, i + 1, line.strip()))

    allowed = {("bob_importer.py", "return list(img.getdata())"),
               ("sprite_importer.py", "return list(img.getdata())")}
    unexpected = [o for o in offenders if (o[0], o[2]) not in allowed]

    assert not unexpected, (
        "Direct .getdata() call outside the compat helper; use flatten_image_pixels():\n  "
        + "\n  ".join(f"{name}:{line_no} {text}" for name, line_no, text in unexpected)
    )
