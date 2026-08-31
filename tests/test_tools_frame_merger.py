"""Tests for tools/frame_merger.py.

frame_merger re-parses already-generated .s files rather than regenerating from
source images, so it must strip each input's own SECTION/XDEF/CNOP prologue and
emit exactly one consolidated set.
"""
from pathlib import Path

import pytest

pytest.importorskip("PIL.Image")

from tests.tools_helpers import assert_section_cnop_invariant, make_png  # noqa: E402
from tools.bob_importer import export_bob_asm  # noqa: E402
from tools.frame_merger import merge_assembly_frames  # noqa: E402


@pytest.fixture
def merged_frames(tmp_path: Path) -> str:
    png = make_png(tmp_path / "frame.png", 16, 2)
    for i in range(3):
        asm = export_bob_asm(str(png), f"frame_{i}", planes=2)
        (tmp_path / f"frame_{i}.s").write_text(asm, encoding="utf-8")

    out = tmp_path / "merged.s"
    merge_assembly_frames(str(tmp_path / "frame_*.s"), str(out))
    return out.read_text(encoding="utf-8")


class TestMergedPrologue:
    def test_emits_exactly_one_section(self, merged_frames: str):
        assert merged_frames.count("SECTION") == 1

    def test_emits_exactly_one_cnop(self, merged_frames: str):
        # Regression: per-file CNOP lines used to leak into the merged body.
        assert merged_frames.count("CNOP") == 1

    def test_section_is_followed_by_cnop(self, merged_frames: str):
        assert_section_cnop_invariant(merged_frames)

    def test_emits_exactly_one_xdef_line(self, merged_frames: str):
        xdef_lines = [l for l in merged_frames.split("\n") if "XDEF" in l]
        assert len(xdef_lines) == 1

    def test_consolidated_xdef_lists_every_frame_label(self, merged_frames: str):
        xdef_line = next(l for l in merged_frames.split("\n") if "XDEF" in l)
        for i in range(3):
            assert f"frame_{i}" in xdef_line
            assert f"frame_{i}_data" in xdef_line


class TestMergedBody:
    def test_all_frame_labels_are_present(self, merged_frames: str):
        for i in range(3):
            assert f"frame_{i}_data:" in merged_frames
            assert f"frame_{i}_mask:" in merged_frames

    def test_leave_palette_label_keeps_only_that_palettes_data(self, tmp_path: Path):
        png = make_png(tmp_path / "frame.png", 16, 2)
        for i in range(2):
            asm = export_bob_asm(str(png), f"frame_{i}", planes=2)
            (tmp_path / f"frame_{i}.s").write_text(asm, encoding="utf-8")

        out = tmp_path / "merged.s"
        merge_assembly_frames(
            str(tmp_path / "frame_*.s"), str(out), leave_palette_label="frame_0_palette"
        )
        merged = out.read_text(encoding="utf-8")
        lines = merged.split("\n")

        # Both labels survive; only the kept one still has DC.W colour data.
        assert "frame_0_palette:" in merged
        assert "frame_1_palette:" in merged
        kept = lines[lines.index("frame_0_palette:") + 1]
        dropped = lines[lines.index("frame_1_palette:") + 1]
        assert kept.strip().upper().startswith("DC.W")
        assert not dropped.strip().upper().startswith("DC.W")


def test_missing_input_pattern_exits_nonzero(tmp_path: Path):
    with pytest.raises(SystemExit) as excinfo:
        merge_assembly_frames(str(tmp_path / "nothing_*.s"), str(tmp_path / "out.s"))
    assert excinfo.value.code != 0
