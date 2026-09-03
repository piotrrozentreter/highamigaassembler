from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
GRAPHICS_S = ROOT / "lib" / "graphics.s"
GRAPHICS_TEST = ROOT / "examples" / "tests" / "compiler" / "graphics_primitives_test.has"


def _read_norm(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_graphics_primitives_are_exported_and_declared():
    graphics_s = _read_norm(GRAPHICS_S)
    graphics_test = _read_norm(GRAPHICS_TEST)

    for name, args in {
        "POINT": 3,
        "PLOT": 3,
        "LINE": 5,
        "RECTANGLE": 5,
        "CIRCLE": 4,
    }.items():
        assert re.search(rf"^\s*XDEF\s+{name}\b", graphics_s, re.MULTILINE)
        declaration = re.search(rf"extern func {name}\(([^)]*)\) -> int;", graphics_test)
        assert declaration, f"Missing HAS declaration for {name}"
        assert len(declaration.group(1).split(",")) == args


def test_setpixel_rejects_unsupported_mode_negative_colors_and_null_screen():
    graphics_s = _read_norm(GRAPHICS_S)
    setpixel = graphics_s[graphics_s.index("_SetPixel:"):graphics_s.index("    SECTION graphics_data,DATA")]

    assert re.search(r"cmp\.w #1,d7\s*\n\s*beq\.w \.sp_hires\s*\n\s*bra\.w \.sp_out_of_bounds", setpixel)
    assert setpixel.count("tst.l d2\n    blt .sp_out_of_bounds") == 2
    assert setpixel.count("cmpa.l #0,a0\n    beq .sp_out_of_bounds") == 2


def test_composite_primitives_plot_through_checked_pixel_api():
    graphics_s = _read_norm(GRAPHICS_S)

    line = graphics_s[graphics_s.index("LINE:"):graphics_s.index("RECTANGLE:")]
    rectangle = graphics_s[graphics_s.index("RECTANGLE:"):graphics_s.index("CIRCLE:")]
    circle = graphics_s[graphics_s.index("CIRCLE:"):graphics_s.index("    SECTION graphics_data,DATA")]

    assert "jsr PLOT" in line
    assert rectangle.count("jsr LINE") == 4
    assert "jsr PLOT" in circle