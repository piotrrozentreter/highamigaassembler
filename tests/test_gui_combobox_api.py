from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
GUI_S = ROOT / "lib" / "gui.s"
GUI_I = ROOT / "lib" / "gui.i"


def _read_norm(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _slice_between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    assert start != -1, f"Missing marker: {start_marker}"
    end = text.find(end_marker, start)
    assert end != -1, f"Missing end marker after {start_marker}: {end_marker}"
    return text[start:end]


def _slice_from_label(text: str, label: str, next_labels: list[str]) -> str:
    start_marker = f"{label}:"
    start = text.find(start_marker)
    assert start != -1, f"Missing label: {start_marker}"

    ends = []
    for next_label in next_labels:
        idx = text.find(f"{next_label}:", start + len(start_marker))
        if idx != -1:
            ends.append(idx)

    end = min(ends) if ends else len(text)
    return text[start:end]


def _assert_regex(text: str, pattern: str, msg: str) -> None:
    assert re.search(pattern, text, re.MULTILINE | re.DOTALL), msg


def test_combobox_symbol_and_type_export_contract():
    gui_s = _read_norm(GUI_S)
    gui_i = _read_norm(GUI_I)

    assert re.search(r"^\s*XDEF\s+DrawComboBox\b", gui_s, re.MULTILINE), (
        "DrawComboBox must be exported from lib/gui.s via XDEF"
    )
    assert re.search(r"^\s*XREF\s+DrawComboBox\b", gui_i, re.MULTILINE), (
        "DrawComboBox must be referenced from lib/gui.i via XREF"
    )

    assert re.search(r"^\s*GADGET_TYPE_COMBOBOX\s+EQU\s+\d+\b", gui_i, re.MULTILINE), (
        "Expected GADGET_TYPE_COMBOBOX EQU constant in lib/gui.i"
    )

    assert "extern func DrawComboBox(gadget_ptr:int) -> int;" in gui_i, (
        "Expected HAS extern declaration for DrawComboBox(gadget_ptr:int) -> int in lib/gui.i"
    )


def test_combobox_selected_field_declared_in_gui_i():
    gui_i = _read_norm(GUI_I)

    assert re.search(r"^\s*COMBOBOX_SELECTED\s+EQU\s+\d+\b", gui_i, re.MULTILINE), (
        "lib/gui.i must define COMBOBOX_SELECTED offset constant"
    )


def test_drawgadget_dispatches_to_combobox_and_does_not_clobber_d0_after_call():
    gui_s = _read_norm(GUI_S)
    block = _slice_between(gui_s, "DrawGadget:", "DrawButton:")

    assert "jsr DrawComboBox" in block, "DrawGadget must dispatch to DrawComboBox for ComboBox type"

    _assert_regex(
        block,
        r"cmp\.w\s+#(?:3|GADGET_TYPE_COMBOBOX),d1\s*\n\s*beq\s+\.\w+",
        "DrawGadget should branch on GADGET_TYPE_COMBOBOX",
    )

    assert not re.search(
        r"jsr\s+DrawComboBox\s*\n\s*(?:lea\s+\d+\(sp\),sp\s*\n\s*)?(?:moveq\s+#0,d0|clr\.l\s+d0|move\.l\s+#0,d0)",
        block,
        re.MULTILINE,
    ), "DrawGadget must preserve DrawComboBox return in d0 (selected index)"


def test_drawcombobox_parses_semicolon_rows_with_nul_height_and_width_bounds():
    gui_s = _read_norm(GUI_S)
    combo = _slice_from_label(
        gui_s,
        "DrawComboBox",
        ["DrawGadget", "DrawButton", "DrawEditBox", "GuiPollMouse", "GuiHitTest"],
    )

    _assert_regex(
        combo,
        r"move\.l\s+12\(a4\),a0\b",
        "DrawComboBox should load list text pointer from GADGET_TEXT",
    )

    _assert_regex(
        combo,
        r"(?:cmp\.b\s+#(?:59|';'),d[0-7]|cmpi?\.b\s+#(?:59|';'),d[0-7])",
        "DrawComboBox should parse semicolon-separated entries",
    )

    _assert_regex(
        combo,
        r"(?:tst\.b\s+d[0-7]|cmp\.b\s+#0,d[0-7]|tst\.b\s+\(a[0-6]\)).*\n\s*beq\b",
        "DrawComboBox should stop parsing on NUL terminator",
    )

    _assert_regex(
        combo,
        r"move\.w\s+6\(a4\),d7[\s\S]*?subq\.l\s+#2,d7[\s\S]*?lsr\.l\s+#3,d7",
        "DrawComboBox should derive max rows from gadget height",
    )

    _assert_regex(
        combo,
        r"move\.w\s+4\(a4\),d5[\s\S]*?sub\.l\s+#16,d5[\s\S]*?lsr\.l\s+#3,d5",
        "DrawComboBox should derive max chars per row from gadget width",
    )

    _assert_regex(
        combo,
        r"tst\.[wl]\s+d[0-7]\s*\n\s*beq\s+\.\w+.*subq\.[wl]\s+#1,d[0-7]",
        "DrawComboBox row rendering should be bounded by a decrementing per-row column counter",
    )


def test_drawcombobox_highlight_store_selected_and_return_index_or_minus_one():
    gui_s = _read_norm(GUI_S)
    gui_i = _read_norm(GUI_I)
    combo = _slice_from_label(
        gui_s,
        "DrawComboBox",
        ["DrawGadget", "DrawButton", "DrawEditBox", "GuiPollMouse", "GuiHitTest"],
    )

    assert "COMBOBOX_SELECTED" in gui_i, "COMBOBOX_SELECTED must exist in gui.i"

    _assert_regex(
        combo,
        r"move\.w\s+20\(a4\),d0",
        "DrawComboBox should read previously selected row from COMBOBOX_SELECTED",
    )

    _assert_regex(
        combo,
        r"move\.w\s+-12\(a6\),20\(a4\)",
        "DrawComboBox should store updated selection in COMBOBOX_SELECTED",
    )

    _assert_regex(
        combo,
        r"move\.l\s+-12\(a6\),d0\s*\n\s*cmp\.l\s+d4,d0\s*\n\s*bne\s+\.dcb_colors_ready",
        "DrawComboBox should detect selected row and branch to a highlight rendering path",
    )
    _assert_regex(
        combo,
        r"\.dcb_row_loop:[\s\S]*?cmp\.l\s+d4,d0\s*\n\s*bne\s+\.dcb_keep_sel\s*\n\s*move\.l\s+d4,-12\(a6\)[\s\S]*?; Select row colors",
        "Clicked row should update selection before row colors are chosen",
    )

    _assert_regex(
        combo,
        r"(?:moveq\s+#-1,d0|move\.l\s+#-1,d0)",
        "DrawComboBox should support -1 return value when no row is selected",
    )

    _assert_regex(
        combo,
        r"(?:move\.[wl]\s+d[0-7],d0|ext\.l\s+d0)",
        "DrawComboBox should return selected index in d0",
    )

