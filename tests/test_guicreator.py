"""Tests for the guicreator metadata layer and HAS emitter.

Deliberately avoids importing guicreator.builder so the suite runs headless
(no Tk display needed on CI or over SSH).
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from guicreator import ControlType, MetadataManager, has_export, hasmeta
from guicreator.model import MAX_GADGETS, MIN_WINDOW_H, MIN_WINDOW_W

ROOT = Path(__file__).resolve().parents[1]


def make_form() -> MetadataManager:
    m = MetadataManager()
    m.window.caption = "Login"
    m.window.width = 320
    m.window.height = 120
    m.add(ControlType.LABEL, 12, 24, caption="Name:", name="lbl_name")
    m.add(ControlType.EDITBOX, 92, 22, 200, 14, name="edit_name", maxlen=32)
    m.add(ControlType.BUTTON, 116, 64, 88, 18, caption="OK", name="btn_ok")
    return m


# ---------------------------------------------------------------------------
# model / ActionID allocation
# ---------------------------------------------------------------------------


def test_action_ids_start_at_one_and_are_unique():
    m = make_form()
    ids = [c.action_id for c in m]
    assert ids == [1, 2, 3]
    assert min(ids) >= 1, "0 is reserved for 'no gadget'"


def test_action_ids_are_not_recycled_after_delete():
    m = make_form()
    m.remove(m.find(2))
    new = m.add(ControlType.BUTTON, 12, 90, caption="Quit")
    assert new.action_id == 4, "IDs must stay stable so handler code keeps working"


def test_id_const_does_not_stutter_when_name_carries_the_prefix():
    m = make_form()
    assert m.find(1).id_const == "ID_LBL_NAME"
    assert m.find(2).id_const == "ID_EDIT_NAME"
    assert m.find(3).id_const == "ID_BTN_OK"


def test_window_flags_never_set_simple_refresh():
    m = make_form()
    flags = m.window.window_flags()
    assert flags == 0x0000100E  # DRAGBAR|DEPTHGADGET|CLOSEGADGET|ACTIVATE
    assert not flags & 0x00000040, "WFLG_SIMPLE_REFRESH must never be emitted"


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def test_valid_form_has_no_problems():
    assert make_form().validate() == []


def test_overlapping_controls_are_rejected():
    m = make_form()
    m.add(ControlType.BUTTON, 116, 68, 88, 18, caption="Dup", name="btn_dup")
    assert any("overlaps" in p for p in m.validate())


def test_control_outside_client_area_is_rejected():
    m = make_form()
    m.find(3).y = 0  # under the drag bar
    assert any("outside the client area" in p for p in m.validate())


def test_undersized_window_is_rejected():
    m = make_form()
    m.window.width = MIN_WINDOW_W - 1
    m.window.height = MIN_WINDOW_H - 1
    m.clear()
    assert any("at least" in p for p in m.validate())


def test_duplicate_names_are_rejected():
    m = make_form()
    m.add(ControlType.BUTTON, 12, 90, 60, 18, caption="X", name="btn_ok")
    assert any("Duplicate control name" in p for p in m.validate())


def test_gadget_pool_limit_is_enforced():
    m = MetadataManager()
    m.window.width, m.window.height = 640, 400
    for i in range(MAX_GADGETS + 1):
        m.add(ControlType.BUTTON, 8, 12 + i * 2, 40, 2, caption="b", name=f"b{i}")
    assert any("GUI_MAX_GADGETS" in p for p in m.validate())


# ---------------------------------------------------------------------------
# .hasmeta round-trip
# ---------------------------------------------------------------------------


def test_hasmeta_round_trips_exactly():
    original = make_form()
    reloaded = hasmeta.loads(hasmeta.render(original, "login"))

    assert reloaded.window == original.window
    assert len(reloaded) == len(original)
    for a, b in zip(original, reloaded):
        assert (a.kind, a.name, a.action_id) == (b.kind, b.name, b.action_id)
        assert (a.x, a.y, a.w, a.h) == (b.x, b.y, b.w, b.h)
        assert a.caption == b.caption
        assert a.maxlen == b.maxlen


def test_hasmeta_emits_required_sections():
    text = hasmeta.render(make_form(), "login")
    for token in (
        "DEFINE_WINDOW",
        "BEGIN_GUI_LAYOUT",
        "END_GUI_LAYOUT",
        "DEFINE_EVENT_HANDLERS START_MODULE",
        "END_EVENT_HANDLERS",
        "SECTION DATA CONSTANTS",
        "END_SECTION",
    ):
        assert token in text


def test_hasmeta_emits_one_handler_per_interactive_control():
    text = hasmeta.render(make_form(), "login")
    assert "HANDLE_ACTION(ID: 3, ACTION: BUTTON_CLICK)" in text
    assert "HANDLE_ACTION(ID: 2, ACTION: EDITBOX_CHANGE)" in text
    assert "ACTION: LABEL" not in text, "labels are static, they emit no handler"


def test_shipped_example_layout_is_valid():
    m = hasmeta.load(ROOT / "guicreator" / "examples" / "login.hasmeta")
    assert len(m) == 3
    assert m.validate() == []


# ---------------------------------------------------------------------------
# .has emission
# ---------------------------------------------------------------------------


def test_has_declares_only_the_runtime_functions_it_calls():
    """hasc turns every extern into an XREF; vasm then warns about unused ones."""
    text = has_export.render(make_form(), "gui_form")
    declared = set(re.findall(r"^\s*extern func (\w+)", text, re.M))
    called = set(re.findall(r"\b(Gui\w+|WB\w+)\s*\(", text))
    assert declared - called == set(), f"declared but never called: {declared - called}"


def test_has_emits_writable_buffers_for_each_editbox():
    text = has_export.render(make_form(), "gui_form")
    assert "bss gui_form_buffers:" in text
    assert "edit_name_buf.b: 32" in text
    assert "edit_name_undo.b: 32" in text, "each string gadget needs its own undo buffer"
    assert "bss_chip" not in text and "data_chip" not in text


def test_has_adds_widgets_before_show():
    text = has_export.render(make_form(), "gui_form")
    assert text.index("GuiAddButton(") < text.index("win = GuiShow()")


def test_user_code_blocks_survive_regeneration():
    m = make_form()
    first = has_export.render(m, "gui_form")
    edited = first.replace(
        "            // TODO: button \"OK\" clicked",
        "            call GuiRedraw();",
    )
    assert "call GuiRedraw();" in edited

    preserved = has_export.extract_user_code(edited)
    m.add(ControlType.BUTTON, 12, 64, 60, 18, caption="Quit", name="btn_quit")
    second = has_export.render(m, "gui_form", user_code=preserved)

    assert "call GuiRedraw();" in second
    assert "ID_BTN_QUIT" in second


def test_generated_source_has_no_bom_and_unix_newlines(tmp_path):
    path = tmp_path / "form.has"
    has_export.save(make_form(), path)
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "the HAS lexer rejects a BOM"
    assert b"\r\n" not in raw


# ---------------------------------------------------------------------------
# end-to-end: the emitted HAS must actually compile
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cpu", ["68000", "68020"])
def test_generated_source_compiles(tmp_path, cpu):
    src = tmp_path / "form.has"
    has_export.save(make_form(), src)
    result = subprocess.run(
        [sys.executable, "-m", "hasc.cli", str(src), "--cpu", cpu,
         "-o", str(tmp_path / f"form_{cpu}.s")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_shipped_example_matches_regenerated_output():
    """examples/gui_login_form.has must not drift from its .hasmeta source."""
    layout = ROOT / "guicreator" / "examples" / "login.hasmeta"
    shipped = (ROOT / "examples" / "gui_login_form.has").read_text(encoding="utf-8")
    regenerated = has_export.render(
        hasmeta.load(layout), "gui_login_form", "guicreator/examples/login.hasmeta"
    )
    drop_timestamp = lambda t: [
        ln for ln in t.splitlines() if not ln.startswith("// Generated")
    ]
    assert drop_timestamp(shipped) == drop_timestamp(regenerated)
