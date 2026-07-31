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


def _assert_regex(text: str, pattern: str, msg: str) -> None:
    assert re.search(pattern, text, re.MULTILINE | re.DOTALL), msg


def test_drawmsgboxcaption_symbol_exported_and_referenced():
    gui_s = _read_norm(GUI_S)
    gui_i = _read_norm(GUI_I)

    assert re.search(r"^\s*XDEF\s+DrawMsgBoxCaption\b", gui_s, re.MULTILINE), (
        "DrawMsgBoxCaption must be exported from lib/gui.s via XDEF"
    )
    assert re.search(r"^\s*XREF\s+DrawMsgBoxCaption\b", gui_i, re.MULTILINE), (
        "DrawMsgBoxCaption must be referenced from lib/gui.i via XREF"
    )

    assert "extern func DrawMsgBoxCaption(" in gui_i, (
        "Expected HAS extern declaration for DrawMsgBoxCaption in lib/gui.i"
    )


def test_drawmsgbox_is_wrapper_calling_caption_with_null_caption_and_9arg_cleanup():
    gui_s = _read_norm(GUI_S)
    block = _slice_between(gui_s, "DrawMsgBox:", ".dmb_exit:")

    assert "jsr DrawMsgBoxCaption" in block, "DrawMsgBox must call DrawMsgBoxCaption"

    assert re.search(r"^\s*move\.l\s+#0,-\(sp\).*$", block, re.MULTILINE), (
        "DrawMsgBox must push caption_ptr=0 for DrawMsgBoxCaption"
    )

    _assert_regex(
        block,
        r"jsr\s+DrawMsgBoxCaption\s*\n\s*lea\s+36\(sp\),sp\b",
        "DrawMsgBox must clean exactly 9 long args (36 bytes) after call",
    )

    pre_call = block.split("jsr DrawMsgBoxCaption", 1)[0]
    pushes = re.findall(r"^\s*move\.l\s+[^,\n]+,-\(sp\)\s*.*$", pre_call, re.MULTILINE)
    assert len(pushes) == 9, f"Expected 9 long pushes before wrapper call, got {len(pushes)}"

    _assert_regex(
        pre_call,
        (
            r"move\.l\s+36\(a6\),-\(sp\).*"
            r"move\.l\s+32\(a6\),-\(sp\).*"
            r"move\.l\s+#0,-\(sp\).*"
            r"move\.l\s+28\(a6\),-\(sp\).*"
            r"move\.l\s+24\(a6\),-\(sp\).*"
            r"move\.l\s+20\(a6\),-\(sp\).*"
            r"move\.l\s+16\(a6\),-\(sp\).*"
            r"move\.l\s+12\(a6\),-\(sp\).*"
            r"move\.l\s+8\(a6\),-\(sp\)"
        ),
        "DrawMsgBox wrapper push order changed unexpectedly",
    )


def test_drawmsgboxcaption_has_bounded_caption_truncation_and_row_reduction():
    gui_s = _read_norm(GUI_S)
    block = _slice_between(gui_s, "DrawMsgBoxCaption:", ".dmbc_exit:")

    _assert_regex(
        block,
        r"move\.l\s+16\(a6\),d3\s*\n\s*lsr\.l\s+#3,d3\s*\n\s*subq\.l\s+#2,d3\b",
        "Expected max_cols computation as w/8 - 2",
    )

    _assert_regex(
        block,
        r"move\.l\s+32\(a6\),a0\b",
        "Caption path should load caption_ptr",
    )
    _assert_regex(
        block,
        r"tst\.l\s+a0\s*\n\s*beq\s+\.dmbc_render_body",
        "Caption rendering should be skipped for null caption_ptr",
    )
    _assert_regex(
        block,
        r"tst\.b\s+\(a0\)\s*\n\s*beq\s+\.dmbc_render_body",
        "Caption rendering should be skipped for empty caption",
    )

    _assert_regex(
        block,
        r"move\.l\s+d3,d6\b",
        "Expected d6 caption counter initialized from computed max_cols (d3)",
    )
    _assert_regex(
        block,
        (
            r"\.dmbc_cap_loop:\s*\n\s*"
            r"tst\.l\s+d6\s*\n\s*beq\s+\.dmbc_cap_done.*"
            r"subq\.l\s+#1,d6\s*\n\s*bra\s+\.dmbc_cap_loop"
        ),
        "Caption loop must be bounded by d6 and decrement once per emitted char",
    )
    _assert_regex(
        block,
        r"cmp\.b\s+#10,d0.*\n\s*beq\s+\.dmbc_cap_done",
        "Caption loop should stop on LF to avoid multi-row caption rendering",
    )
    _assert_regex(
        block,
        r"cmp\.b\s+#13,d0.*\n\s*beq\s+\.dmbc_cap_done",
        "Caption loop should stop on CR to avoid multi-row caption rendering",
    )

    _assert_regex(
        block,
        r"\.dmbc_cap_done:\s*\n\s*addq\.l\s+#1,d2.*\n\s*subq\.l\s+#1,d4\b",
        "Caption-present path must increment body start row and reduce available rows",
    )
