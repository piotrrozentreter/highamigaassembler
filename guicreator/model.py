"""Data architecture for the GUI Creator (Phase 1 deliverable).

Holds the window definition plus an ordered list of control objects and owns the
mandatory ActionID counter (Phase 2). Everything here is pure data + validation;
no Tkinter, no file formats.

Coordinates are **window-relative pixels**, i.e. (0,0) is the outer top-left of
the Intuition window, underneath the drag bar. Because the generated runtime
deliberately avoids WFLG_GIMMEZEROZERO, the designer canvas origin is inset by
(BORDER_LEFT, BORDER_TOP) so emitted gadget coordinates need no runtime fixup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterator, List, Optional

# Topaz-8 Workbench border thickness. Matches Window.wd_BorderLeft/Top/Right/Bottom.
BORDER_LEFT = 4
BORDER_TOP = 11
BORDER_RIGHT = 4
BORDER_BOTTOM = 2

# Intuition refuses to open anything smaller than this with system gadgets.
MIN_WINDOW_W = 90
MIN_WINDOW_H = 26

# Static pool sizes in lib/gui_intuition.s. Exceeding them is a hard error.
MAX_GADGETS = 32
MAX_LABELS = 32

# Topaz-8 cell metrics, used for auto-sizing labels and centring captions.
CHAR_W = 8
CHAR_H = 8

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ControlType(Enum):
    """Widget kinds supported by the MVP toolbox."""

    LABEL = "LABEL"
    BUTTON = "BUTTON"
    EDITBOX = "EDITBOX"

    @property
    def numeric(self) -> int:
        """Value emitted as CONTROL_TYPE_* in the .hasmeta constants block."""
        return {"LABEL": 0, "BUTTON": 1, "EDITBOX": 2}[self.value]

    @property
    def interactive(self) -> bool:
        """True when the control produces IDCMP events and needs a handler."""
        return self is not ControlType.LABEL

    @property
    def action(self) -> Optional[str]:
        """HANDLE_ACTION verb for this control, or None for static decoration."""
        return {
            ControlType.BUTTON: "BUTTON_CLICK",
            ControlType.EDITBOX: "EDITBOX_CHANGE",
        }.get(self)


@dataclass
class Control:
    """One placed widget: geometry, text payload and its unique ActionID."""

    kind: ControlType
    name: str
    action_id: int
    x: int
    y: int
    w: int
    h: int
    caption: str = ""
    maxlen: int = 32  # EditBox only; counts the terminating NUL.

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def overlaps(self, other: "Control") -> bool:
        return not (
            self.right <= other.x
            or other.right <= self.x
            or self.bottom <= other.y
            or other.bottom <= self.y
        )

    # -- derived assembler symbol names -----------------------------------
    @property
    def id_const(self) -> str:
        stem = {"LABEL": "LBL", "BUTTON": "BTN", "EDITBOX": "EDIT"}[self.kind.value]
        upper = self.name.upper()
        # Avoid ID_BTN_BTN_OK when the name already carries the widget prefix.
        if upper.startswith(stem + "_"):
            return f"ID_{upper}"
        return f"ID_{stem}_{upper}"

    @property
    def text_symbol(self) -> str:
        return f"{self.name}_text"

    @property
    def buffer_symbol(self) -> str:
        return f"{self.name}_buf"

    @property
    def undo_symbol(self) -> str:
        return f"{self.name}_undo"

    @property
    def maxlen_const(self) -> str:
        return f"{self.name.upper()}_MAXLEN"


@dataclass
class WindowSpec:
    """Global window settings (spec III.3.1 'Global Settings')."""

    caption: str = "HAS Form"
    width: int = 320
    height: int = 140
    left: int = 40
    top: int = 30
    dragbar: bool = True
    depth_gadget: bool = True
    close_gadget: bool = True
    activate: bool = True
    sizeable: bool = False

    # WFLG_* bit values (see docs/GUI_INTUITION_RUNTIME_SPEC.md section 2.3).
    _WFLG = {
        "sizeable": 0x00000001 | 0x00000020 | 0x00000010,  # SIZEGADGET|SIZEBBOTTOM|SIZEBRIGHT
        "dragbar": 0x00000002,
        "depth_gadget": 0x00000004,
        "close_gadget": 0x00000008,
        "activate": 0x00001000,
    }

    def window_flags(self) -> int:
        """nw_Flags. WFLG_SMART_REFRESH is zero, so it is never OR'd in."""
        flags = 0
        for attr, bit in self._WFLG.items():
            if getattr(self, attr):
                flags |= bit
        return flags

    @property
    def client_left(self) -> int:
        return BORDER_LEFT

    @property
    def client_top(self) -> int:
        return BORDER_TOP

    @property
    def client_right(self) -> int:
        return self.width - (BORDER_RIGHT + (14 if self.sizeable else 0))

    @property
    def client_bottom(self) -> int:
        return self.height - (BORDER_BOTTOM + (9 if self.sizeable else 0))


# IDCMP_* bits the generated form always subscribes to.
IDCMP_REFRESHWINDOW = 0x00000004
IDCMP_MOUSEBUTTONS = 0x00000008
IDCMP_GADGETDOWN = 0x00000020
IDCMP_GADGETUP = 0x00000040
IDCMP_CLOSEWINDOW = 0x00000200
IDCMP_VANILLAKEY = 0x00200000

DEFAULT_IDCMP = (
    IDCMP_REFRESHWINDOW
    | IDCMP_MOUSEBUTTONS
    | IDCMP_GADGETDOWN
    | IDCMP_GADGETUP
    | IDCMP_CLOSEWINDOW
    | IDCMP_VANILLAKEY
)


class MetadataManager:
    """Owns the window spec, the control list and the ActionID allocator."""

    def __init__(self, window: Optional[WindowSpec] = None) -> None:
        self.window: WindowSpec = window or WindowSpec()
        self.controls: List[Control] = []
        self._next_action_id: int = 1  # 0 is reserved for "no gadget".

    # -- container protocol ------------------------------------------------
    def __len__(self) -> int:
        return len(self.controls)

    def __iter__(self) -> Iterator[Control]:
        return iter(self.controls)

    def by_kind(self, kind: ControlType) -> List[Control]:
        return [c for c in self.controls if c.kind is kind]

    def find(self, action_id: int) -> Optional[Control]:
        return next((c for c in self.controls if c.action_id == action_id), None)

    # -- mutation ----------------------------------------------------------
    def add(
        self,
        kind: ControlType,
        x: int,
        y: int,
        w: Optional[int] = None,
        h: Optional[int] = None,
        caption: Optional[str] = None,
        name: Optional[str] = None,
        maxlen: int = 32,
        action_id: Optional[int] = None,
    ) -> Control:
        """Place a control and allocate its ActionID.

        The counter advances for every control, not only interactive ones, so
        that labels remain individually addressable via GuiSetLabelText().
        """
        caption = caption if caption is not None else self._default_caption(kind)
        w, h = self._default_size(kind, caption, w, h)
        name = name or self._unique_name(kind)

        if action_id is None:
            action_id = self._next_action_id
        self._next_action_id = max(self._next_action_id, action_id) + 1

        control = Control(
            kind=kind,
            name=name,
            action_id=action_id,
            x=int(x),
            y=int(y),
            w=int(w),
            h=int(h),
            caption=caption,
            maxlen=int(maxlen),
        )
        self.controls.append(control)
        return control

    def remove(self, control: Control) -> None:
        """Drop a control. ActionIDs are never recycled, keeping them stable
        across regeneration so hand-edited handler bodies stay valid."""
        self.controls.remove(control)

    def move(self, control: Control, index: int) -> None:
        """Reorder a control; list order is the Intuition TAB cycle order."""
        self.controls.remove(control)
        self.controls.insert(max(0, min(index, len(self.controls))), control)

    def clear(self) -> None:
        self.controls.clear()
        self._next_action_id = 1

    # -- validation --------------------------------------------------------
    def validate(self) -> List[str]:
        """Return human-readable problems; empty list means safe to export."""
        problems: List[str] = []
        win = self.window

        if win.width < MIN_WINDOW_W or win.height < MIN_WINDOW_H:
            problems.append(
                f"Window is {win.width}x{win.height}; Intuition needs at least "
                f"{MIN_WINDOW_W}x{MIN_WINDOW_H} for a window with system gadgets."
            )
        if not win.caption.strip():
            problems.append("Window caption is empty.")

        gadgets = [c for c in self.controls if c.kind.interactive]
        labels = self.by_kind(ControlType.LABEL)
        if len(gadgets) > MAX_GADGETS:
            problems.append(
                f"{len(gadgets)} gadgets exceeds GUI_MAX_GADGETS ({MAX_GADGETS})."
            )
        if len(labels) > MAX_LABELS:
            problems.append(
                f"{len(labels)} labels exceeds GUI_MAX_LABELS ({MAX_LABELS})."
            )

        seen_ids: Dict[int, str] = {}
        seen_names: Dict[str, int] = {}
        for c in self.controls:
            if c.action_id < 1:
                problems.append(f"'{c.name}' has ActionID {c.action_id}; IDs must be >= 1.")
            if c.action_id in seen_ids:
                problems.append(
                    f"Duplicate ActionID {c.action_id}: '{c.name}' and '{seen_ids[c.action_id]}'."
                )
            seen_ids[c.action_id] = c.name

            if not _IDENT_RE.match(c.name):
                problems.append(f"'{c.name}' is not a valid HAS identifier.")
            if c.name in seen_names:
                problems.append(f"Duplicate control name '{c.name}'.")
            seen_names[c.name] = c.action_id

            if c.w < 1 or c.h < 1:
                problems.append(f"'{c.name}' has a degenerate size {c.w}x{c.h}.")
            if (
                c.x < win.client_left
                or c.y < win.client_top
                or c.right > win.client_right
                or c.bottom > win.client_bottom
            ):
                problems.append(
                    f"'{c.name}' at ({c.x},{c.y},{c.w},{c.h}) falls outside the client area "
                    f"({win.client_left},{win.client_top})-({win.client_right},{win.client_bottom})."
                )
            if c.kind is ControlType.EDITBOX:
                if c.maxlen < 2:
                    problems.append(f"'{c.name}' maxlen {c.maxlen} leaves no room for text + NUL.")
                if c.w < CHAR_W + 4:
                    problems.append(f"'{c.name}' is too narrow to show a single character.")

        for i, a in enumerate(self.controls):
            for b in self.controls[i + 1 :]:
                if a.overlaps(b):
                    problems.append(
                        f"'{a.name}' overlaps '{b.name}'; Intuition hit-testing takes the "
                        "first list match, so overlap is always a layout bug."
                    )
        return problems

    # -- helpers -----------------------------------------------------------
    def _default_caption(self, kind: ControlType) -> str:
        n = len(self.by_kind(kind)) + 1
        return {
            ControlType.LABEL: f"Label {n}",
            ControlType.BUTTON: f"Button{n}",
            ControlType.EDITBOX: "",
        }[kind]

    @staticmethod
    def _default_size(
        kind: ControlType, caption: str, w: Optional[int], h: Optional[int]
    ) -> tuple:
        if kind is ControlType.LABEL:
            return (w or max(CHAR_W, len(caption) * CHAR_W), h or CHAR_H)
        if kind is ControlType.BUTTON:
            return (w or max(56, len(caption) * CHAR_W + 16), h or 18)
        return (w or 160, h or 14)

    def _unique_name(self, kind: ControlType) -> str:
        stem = {"LABEL": "lbl", "BUTTON": "btn", "EDITBOX": "edit"}[kind.value]
        taken = {c.name for c in self.controls}
        i = 1
        while f"{stem}_{i}" in taken:
            i += 1
        return f"{stem}_{i}"
