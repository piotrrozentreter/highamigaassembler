from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
GRAPHICS_S = ROOT / "lib" / "graphics.s"


def _read_norm(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _label_pos(text: str, label: str) -> int:
    # Real asm labels stand alone on their own line; a bare substring search
    # can accidentally match the same name mentioned inside a preceding
    # comment line instead of the actual label further down.
    match = re.search(rf"^{re.escape(label)}[ \t]*$", text, re.MULTILINE)
    assert match, f"label not found on its own line: {label}"
    return match.start()


def _slice(text: str, start_label: str, end_label: str) -> str:
    return text[_label_pos(text, start_label):_label_pos(text, end_label)]


# ---------------------------------------------------------------------------
# ScrollHorizontalScreen (lib/graphics.s)
# ---------------------------------------------------------------------------

def test_scrollhorizontalscreen_is_exported_and_declared():
    graphics_s = _read_norm(GRAPHICS_S)
    assert re.search(r"^\s*XDEF\s+ScrollHorizontalScreen\b", graphics_s, re.MULTILINE)
    assert re.search(r"^ScrollHorizontalScreen:", graphics_s, re.MULTILINE)


def test_bplcon1_shadow_variable_declared_once():
    graphics_s = _read_norm(GRAPHICS_S)
    assert re.search(r"^gfx_bplcon1_shadow:\s*\n\s*dc\.w 0", graphics_s, re.MULTILINE)


def test_scrollhorizontalscreen_validates_px_range_before_mode():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, "ScrollHorizontalScreen:", "Text:")

    # Range check (-15..15) must happen on the full .l parameter, before any
    # mode check, matching Scroll()'s own "validate numbers, then mode" order.
    range_check = re.search(
        r"move\.l 8\(a6\),d0\s*\n\s*cmp\.l #15,d0\s*\n\s*bgt \.shs_error"
        r"\s*\n\s*cmp\.l #-15,d0\s*\n\s*blt \.shs_error",
        block,
    )
    assert range_check
    mode_check = re.search(r"cmp\.w #2,gfx_current_mode\s*\n\s*beq \.shs_error", block)
    assert mode_check
    assert range_check.start() < mode_check.start()


def test_scrollhorizontalscreen_rejects_ham6_only():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, "ScrollHorizontalScreen:", "Text:")
    # HAM6 (mode 2) is the only explicit mode rejection - modes 0, 1, 3 fall
    # through to the encoding logic.
    assert block.count("gfx_current_mode") == 2  # HAM6 reject + mode-3 dispatch


def test_scrollhorizontalscreen_encodes_signed_px_into_nibble():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, "ScrollHorizontalScreen:", "Text:")

    # px>=0 -> nibble = px directly.
    assert re.search(
        r"tst\.l d0\s*\n\s*blt\.s \.shs_negative\s*\n\s*move\.w d0,d1", block
    )
    # px<0 -> nibble = 15-|px|.
    assert re.search(
        r"\.shs_negative:\s*\n\s*neg\.l d0\s*\n\s*moveq #15,d1\s*\n\s*sub\.w d0,d1",
        block,
    )


def test_scrollhorizontalscreen_dualpf_preserves_sibling_nibble():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, "ScrollHorizontalScreen:", "Text:")

    assert re.search(r"cmp\.w #3,gfx_current_mode\s*\n\s*bne\.s \.shs_single", block)
    # PF1 path clears bits 0-3 only; PF2 path shifts the nibble up 4 bits and
    # clears bits 4-7 only - both preserve the untouched sibling bits.
    assert re.search(r"and\.w #\$FFF0,d0", block)
    assert re.search(r"lsl\.w #4,d1\s*\n\s*and\.w #\$FF0F,d0", block)
    # Both dualpf branches read/write the shared shadow, never BPLCON1 directly
    # mid-computation.
    assert block.count("gfx_bplcon1_shadow") == 2  # one read, one write


def test_scrollhorizontalscreen_single_playfield_mirrors_both_nibbles():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, ".shs_single:", ".shs_write:")
    assert re.search(r"move\.w d1,d0\s*\n\s*lsl\.w #4,d0\s*\n\s*or\.w d1,d0", block)


def test_scrollhorizontalscreen_writes_hardware_register_and_shadow_together():
    graphics_s = _read_norm(GRAPHICS_S)
    block = _slice(graphics_s, ".shs_write:", ".shs_error:")
    assert re.search(
        r"move\.w d0,gfx_bplcon1_shadow\s*\n\s*move\.w d0,BPLCON1\(a5\)", block
    )


def test_all_four_mode_inits_reset_bplcon1_shadow():
    graphics_s = _read_norm(GRAPHICS_S)
    # SetGraphicsMode has exactly 4 mode branches (lores, hires, HAM6, dualpf);
    # each must reset the shadow in lockstep with the hardware register so a
    # later mode switch can't leave a stale nibble behind.
    resets = re.findall(r"move\.w #0,BPLCON1\(a5\)\s*; No scroll\s*\n\s*move\.w #0,gfx_bplcon1_shadow", graphics_s)
    assert len(resets) == 4
