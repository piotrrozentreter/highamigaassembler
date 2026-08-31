"""Tests for tools/sprite_importer.py (hardware sprite packing and emission)."""
import warnings
from pathlib import Path

import pytest

pytest.importorskip("PIL.Image")

from tests.tools_helpers import assert_section_cnop_invariant, make_png  # noqa: E402
from tools.sprite_importer import (  # noqa: E402
    ensure_width,
    export_sprite_asm,
    flatten_image_pixels,
    pack_planar_rows_hardware_sprite,
)
from PIL import Image  # noqa: E402


def _indexed(width: int, height: int, indices):
    img = Image.new("P", (width, height))
    img.putdata(indices)
    return img


class TestHardwareSpritePacking:
    def test_bits_are_packed_msb_first(self):
        rows = pack_planar_rows_hardware_sprite(_indexed(16, 1, [3] + [0] * 15))
        assert rows == [(0x8000, 0x8000)]

    def test_index_selects_the_matching_plane_bit(self):
        # index 1 -> plane0 only, index 2 -> plane1 only.
        rows = pack_planar_rows_hardware_sprite(_indexed(16, 2, [1] * 16 + [2] * 16))
        assert rows == [(0xFFFF, 0x0000), (0x0000, 0xFFFF)]

    def test_narrow_images_are_left_aligned_in_the_word(self):
        rows = pack_planar_rows_hardware_sprite(_indexed(8, 1, [1] * 8))
        assert rows == [(0xFF00, 0x0000)]

    def test_one_row_emitted_per_scanline(self):
        rows = pack_planar_rows_hardware_sprite(_indexed(16, 5, [0] * 80))
        assert len(rows) == 5

    def test_ensure_width_resizes_to_16(self):
        assert ensure_width(Image.new("P", (8, 4)), 16).width == 16
        unchanged = Image.new("P", (16, 4))
        assert ensure_width(unchanged, 16) is unchanged


class TestAssemblyEmission:
    def test_sprite_templates_live_in_fast_ram(self, tmp_path: Path):
        png = make_png(tmp_path / "spr.png", 16, 4)
        asm = export_sprite_asm(str(png), "test_spr")

        # Templates are CPU-copied into chip RAM by CreateSprite, so DATA is correct.
        assert "\tSECTION sprite_templates,DATA" in asm
        assert "DATA_C" not in asm
        assert_section_cnop_invariant(asm)

    def test_exports_expected_labels(self, tmp_path: Path):
        png = make_png(tmp_path / "spr.png", 16, 4)
        asm = export_sprite_asm(str(png), "test_spr")

        assert "\tXDEF\ttest_spr, test_spr_palette" in asm
        assert "test_spr:" in asm
        assert "test_spr_palette:" in asm

    def test_palette_has_four_entries_with_transparent_first(self, tmp_path: Path):
        png = make_png(tmp_path / "spr.png", 16, 4)
        asm = export_sprite_asm(str(png), "test_spr")
        lines = asm.split("\n")
        start = lines.index("test_spr_palette:")
        palette = [line for line in lines[start + 1:start + 5]]

        assert len(palette) == 4
        assert palette[0].startswith("\tDC.W\t$000")
        assert "transparent" in palette[0]

    def test_data_block_is_height_controls_rows_then_terminator(self, tmp_path: Path):
        png = make_png(tmp_path / "spr.png", 16, 3)
        asm = export_sprite_asm(str(png), "test_spr")
        lines = asm.split("\n")
        start = lines.index("test_spr:")

        assert lines[start + 1] == "\tDC.W\t3"
        assert lines[start + 2].startswith("\tDC.W\t$")
        # 3 scanlines of paired plane words, then the terminator.
        assert all(line.startswith("\tDC.W\t%") for line in lines[start + 3:start + 6])
        assert lines[start + 6] == "\tDC.W\t0,0"

    def test_vstart_is_encoded_in_the_first_control_word(self, tmp_path: Path):
        png = make_png(tmp_path / "spr.png", 16, 2)
        asm = export_sprite_asm(str(png), "test_spr", vstart=0x20)
        lines = asm.split("\n")
        start = lines.index("test_spr:")
        control1 = lines[start + 2].split(",")[0].split("$")[1]

        # VSTART in the high byte, VSTOP (vstart + height) in the low byte.
        assert control1 == "2022"

    def test_directives_are_uppercase(self, tmp_path: Path):
        png = make_png(tmp_path / "spr.png", 16, 2)
        asm = export_sprite_asm(str(png), "test_spr")

        for lowercase in ("\tsection ", "\txdef\t", "\tdc.w\t", "\tcnop\t"):
            assert lowercase not in asm


class TestPillowCompat:
    def test_flatten_matches_legacy_pixel_order(self):
        img = Image.new("RGB", (2, 1))
        img.putdata([(1, 1, 1), (2, 2, 2)])

        assert flatten_image_pixels(img) == [(1, 1, 1), (2, 2, 2)]

    def test_export_emits_no_deprecation_warning(self, tmp_path: Path):
        png = make_png(tmp_path / "spr.png", 16, 2)

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            export_sprite_asm(str(png), "test_spr")
