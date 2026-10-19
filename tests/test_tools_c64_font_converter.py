"""Tests for tools/c64_font_converter.py (C64 charset → Amiga font table)."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from tools.c64_font_converter import (  # noqa: E402
    export_font_asm,
    load_c64_font,
    read_c64_font_bin,
)


def _write_bin(path: Path, glyphs: Dict[int, bytes]) -> Path:
    """Write a dense chargen starting at screen code 0 up to max key."""
    max_code = max(glyphs) if glyphs else -1
    data = bytearray((max_code + 1) * 8)
    for code, rows in glyphs.items():
        assert len(rows) == 8
        data[code * 8 : (code + 1) * 8] = rows
    path.write_bytes(data)
    return path


class TestBinReader:
    def test_reads_sequential_screen_codes(self, tmp_path: Path):
        a = bytes([0x18, 0x3C, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00])
        path = _write_bin(tmp_path / "font.bin", {0: bytes(8), 1: a})
        glyphs = read_c64_font_bin(path)
        assert glyphs[0] == [0] * 8
        assert glyphs[1] == list(a)

    def test_rejects_non_multiple_of_8(self, tmp_path: Path):
        path = tmp_path / "bad.bin"
        path.write_bytes(b"\x00" * 7)
        with pytest.raises(ValueError, match="multiple of 8"):
            read_c64_font_bin(path)

    def test_rejects_empty(self, tmp_path: Path):
        path = tmp_path / "empty.bin"
        path.write_bytes(b"")
        with pytest.raises(ValueError, match="empty"):
            read_c64_font_bin(path)


class TestLoadDispatch:
    def test_bin_and_asm_extensions(self, tmp_path: Path):
        a = bytes([0x18, 0x3C, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00])
        bin_path = _write_bin(tmp_path / "f.bin", {1: a})
        asm_path = tmp_path / "f.s"
        asm_path.write_text(
            "\tdc.b $00,$00,$00,$00,$00,$00,$00,$00\n"
            "\tdc.b $18,$3C,$66,$7E,$66,$66,$66,$00\n",
            encoding="utf-8",
        )
        assert load_c64_font(bin_path)[1] == list(a)
        assert load_c64_font(asm_path)[1] == list(a)

    def test_unsupported_extension(self, tmp_path: Path):
        path = tmp_path / "font.png"
        path.write_bytes(b"nope")
        with pytest.raises(ValueError, match="unsupported"):
            load_c64_font(path)


class TestExportFontAsm:
    def test_bin_round_trip_plane0_bytes(self, tmp_path: Path):
        a = bytes([0x18, 0x3C, 0x66, 0x7E, 0x66, 0x66, 0x66, 0x00])
        path = _write_bin(tmp_path / "charset.bin", {1: a})
        asm = export_font_asm(path, "my_font")
        assert "\tSECTION fonts,DATA" in asm
        assert "\tXDEF\tmy_font" in asm
        assert "my_font:" in asm
        # 96 glyphs × 40 bytes = 3840 hex tokens ($XX)
        tokens = [t for t in asm.replace(",", " ").split() if t.startswith("$")]
        assert len(tokens) == 96 * 40
        # Glyph index for 'A' is ascii 65-32 = 33; plane0 is first 8 of 40-byte slot
        glyph_a_offset = 33 * 40
        plane0 = tokens[glyph_a_offset : glyph_a_offset + 8]
        assert plane0 == [f"${b:02X}" for b in a]
        # Planes 1-4 of that glyph are zero
        rest = tokens[glyph_a_offset + 8 : glyph_a_offset + 40]
        assert all(t == "$00" for t in rest)

    def test_asm_export_still_works(self, tmp_path: Path):
        path = tmp_path / "charset.s"
        path.write_text(
            "\tdc.b $00,$00,$00,$00,$00,$00,$00,$00\n"
            "\tdc.b $FF,$81,$81,$81,$81,$81,$81,$FF\n",
            encoding="utf-8",
        )
        asm = export_font_asm(path, "fonts_test")
        assert "fonts_test:" in asm
        assert "SECTION fonts,DATA" in asm
