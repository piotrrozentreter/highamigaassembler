from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
INPUT_S = ROOT / "lib" / "input.s"


def _read_norm(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _slice_between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    assert start != -1, f"Missing marker: {start_marker}"
    end = text.find(end_marker, start)
    assert end != -1, f"Missing end marker after {start_marker}: {end_marker}"
    return text[start:end]


def _getter_block(text: str, label: str) -> str:
    start = text.find(f"{label}:")
    assert start != -1, f"Missing label: {label}"
    end = text.find(";----------------------------------------------------------------", start + len(label) + 1)
    return text[start:end if end != -1 else len(text)]


def test_mouse_button_edge_storage_and_exports():
    input_s = _read_norm(INPUT_S)

    for button in ("lbtn", "rbtn"):
        for suffix in ("prev", "pressed", "released"):
            assert re.search(
                rf"^mouse_{button}_{suffix}\s+dc\.w\s+0\b", input_s, re.MULTILINE
            ), f"mouse_{button}_{suffix} must retain button edge state"

    for getter in (
        "GetMouseLBtnPressed",
        "GetMouseLBtnReleased",
        "GetMouseRBtnPressed",
        "GetMouseRBtnReleased",
    ):
        assert re.search(rf"^\s*xdef\s+{getter}\b", input_s, re.MULTILINE), (
            f"{getter} must be exported"
        )


def test_readmouse_snapshots_levels_and_derives_button_edges():
    input_s = _read_norm(INPUT_S)
    read_mouse = _slice_between(input_s, "ReadMouse:", ";----------------------------------------------------------------\n; Function: GetMouseX")

    left_snapshot = read_mouse.find("move.w     mouse_lbtn,mouse_lbtn_prev")
    left_sample = read_mouse.find("btst       #6,CIAAPRA")
    right_snapshot = read_mouse.find("move.w     mouse_rbtn,mouse_rbtn_prev")
    right_sample = read_mouse.find("btst       #2,POTINP(a5)")
    edge_update = read_mouse.find(".update_btn_edges:")

    assert -1 not in (left_snapshot, left_sample, right_snapshot, right_sample, edge_update)
    assert left_snapshot < left_sample < edge_update
    assert right_snapshot < right_sample < edge_update

    for button in ("lbtn", "rbtn"):
        assert re.search(
            rf"move\.w\s+mouse_{button}_prev,d0\s*\n\s*not\.w\s+d0\s*\n"
            rf"\s*and\.w\s+mouse_{button},d0\s*\n\s*move\.w\s+d0,mouse_{button}_pressed",
            read_mouse,
        ), f"mouse_{button}_pressed must be current AND NOT previous"
        assert re.search(
            rf"move\.w\s+mouse_{button},d0\s*\n\s*not\.w\s+d0\s*\n"
            rf"\s*and\.w\s+mouse_{button}_prev,d0\s*\n\s*move\.w\s+d0,mouse_{button}_released",
            read_mouse,
        ), f"mouse_{button}_released must be previous AND NOT current"


def test_mouse_button_getters_return_sign_extended_words():
    input_s = _read_norm(INPUT_S)

    getters = {
        "GetMouseLBtn": "mouse_lbtn",
        "GetMouseRBtn": "mouse_rbtn",
        "GetMouseLBtnPressed": "mouse_lbtn_pressed",
        "GetMouseLBtnReleased": "mouse_lbtn_released",
        "GetMouseRBtnPressed": "mouse_rbtn_pressed",
        "GetMouseRBtnReleased": "mouse_rbtn_released",
    }
    for getter, state in getters.items():
        block = _getter_block(input_s, getter)
        assert re.search(
            rf"move\.w\s+{state},d0\s*\n\s*ext\.l\s+d0\s*\n\s*rts", block
        ), f"{getter} must return {state} as a sign-extended longword"