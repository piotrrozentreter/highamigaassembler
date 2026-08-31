"""Tests for tools/bob_importer.py (BOB planar packing and assembly emission)."""
import warnings
from pathlib import Path

import pytest

pytest.importorskip("PIL.Image")

from tests.tools_helpers import (  # noqa: E402
    assert_section_cnop_invariant,
    data_words,
    make_png,
)
from tools.bob_importer import (  # noqa: E402
    _pack_planar_row_chunk,
    export_bob_asm,
    flatten_image_pixels,
    quantize_image,
)
from PIL import Image  # noqa: E402


class TestPlanarPacking:
    def test_bits_are_packed_msb_first(self):
        # index 3 at x=0 sets the top bit of both planes; x=1 is index 0.
        words = _pack_planar_row_chunk([3, 0], chunk_x=0, width=2, planes=2)
        assert words == [0x8000, 0x8000]

    def test_plane_bit_is_taken_from_matching_index_bit(self):
        # index 2 = binary 10 -> plane0 clear, plane1 set.
        words = _pack_planar_row_chunk([2], chunk_x=0, width=1, planes=2)
        assert words == [0x0000, 0x8000]

    def test_pixels_past_image_width_pad_with_zero(self):
        words = _pack_planar_row_chunk([1] * 16, chunk_x=16, width=16, planes=1)
        assert words == [0x0000]

    def test_full_row_of_ones_fills_the_word(self):
        words = _pack_planar_row_chunk([1] * 16, chunk_x=0, width=16, planes=1)
        assert words == [0xFFFF]

    def test_word_never_exceeds_16_bits(self):
        words = _pack_planar_row_chunk([31] * 16, chunk_x=0, width=16, planes=5)
        assert all(0 <= w <= 0xFFFF for w in words)


class TestAssemblyEmission:
    def test_section_is_chip_ram_and_followed_by_cnop(self, tmp_path: Path):
        png = make_png(tmp_path / "bob.png", 16, 2)
        asm = export_bob_asm(str(png), "test_bob", planes=2)

        # BOB pixel data is blitter DMA source, so chip RAM is correct here.
        assert "\tSECTION bobs,DATA_C" in asm
        assert_section_cnop_invariant(asm)

    def test_exports_expected_labels(self, tmp_path: Path):
        png = make_png(tmp_path / "bob.png", 16, 2)
        asm = export_bob_asm(str(png), "test_bob", planes=2)

        assert "\tXDEF\ttest_bob, test_bob_data, test_bob_mask, test_bob_palette" in asm
        for label in ("test_bob_data:", "test_bob_mask:", "test_bob_palette:"):
            assert label in asm

    def test_data_header_is_width_then_height(self, tmp_path: Path):
        png = make_png(tmp_path / "bob.png", 16, 3)
        asm = export_bob_asm(str(png), "test_bob", planes=2)

        assert data_words(asm, "test_bob_data")[:2] == ["16", "3"]

    def test_add_word_widens_the_stored_header_width_by_16(self, tmp_path: Path):
        png = make_png(tmp_path / "bob.png", 16, 2)
        plain = export_bob_asm(str(png), "test_bob", planes=2, add_word=False)
        widened = export_bob_asm(str(png), "test_bob", planes=2, add_word=True)

        assert data_words(plain, "test_bob_data")[:2] == ["16", "2"]
        assert data_words(widened, "test_bob_data")[:2] == ["32", "2"]

    def test_non_multiple_of_16_width_rounds_up_but_header_keeps_original(self, tmp_path: Path):
        png = make_png(tmp_path / "bob.png", 20, 2)
        asm = export_bob_asm(str(png), "test_bob", planes=2)

        # Header advertises the true width; planar data is padded to 32px (2 chunks).
        assert data_words(asm, "test_bob_data")[:2] == ["20", "2"]
        assert "converted width=32px (2 chunks)" in asm

    def test_directives_are_uppercase(self, tmp_path: Path):
        png = make_png(tmp_path / "bob.png", 16, 2)
        asm = export_bob_asm(str(png), "test_bob", planes=2)

        for lowercase in ("\tsection ", "\txdef\t", "\tdc.w\t", "\tcnop\t"):
            assert lowercase not in asm


class TestQuantize:
    def test_returns_one_index_row_per_scanline(self, tmp_path: Path):
        png = make_png(tmp_path / "bob.png", 16, 4)
        quant = quantize_image(str(png), planes=2)

        assert quant["width"] == 16
        assert quant["height"] == 4
        assert len(quant["indices_by_row"]) == 4
        assert all(len(row) == 16 for row in quant["indices_by_row"])

    def test_indices_stay_within_the_plane_budget(self, tmp_path: Path):
        png = make_png(tmp_path / "bob.png", 16, 4)
        quant = quantize_image(str(png), planes=2)

        assert all(0 <= idx < 4 for row in quant["indices_by_row"] for idx in row)

    def test_fully_transparent_pixels_are_detected(self, tmp_path: Path):
        png = make_png(tmp_path / "bob.png", 16, 2, colors=[(255, 0, 0, 255), (0, 0, 0, 0)])
        quant = quantize_image(str(png), planes=2)

        assert quant["has_transparent"] is True


class TestPillowCompat:
    def test_flatten_matches_legacy_pixel_order(self):
        img = Image.new("RGB", (2, 2))
        img.putdata([(1, 1, 1), (2, 2, 2), (3, 3, 3), (4, 4, 4)])

        assert flatten_image_pixels(img) == [(1, 1, 1), (2, 2, 2), (3, 3, 3), (4, 4, 4)]

    def test_export_emits_no_deprecation_warning(self, tmp_path: Path):
        png = make_png(tmp_path / "bob.png", 16, 2)

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            export_bob_asm(str(png), "test_bob", planes=2)
