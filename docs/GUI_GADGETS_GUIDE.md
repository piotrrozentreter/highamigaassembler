# Guicreator gadgets — developer’s guide

Practical guide to the **six** widget types that guicreator designs and that the
Intuition runtime drives from **HAS** (`lib/gui_intuition.s`) and **pythonami**
(`gui_intuition.py68k`).

| Companion doc | Role |
| --- | --- |
| [GUI_CREATOR.md](GUI_CREATOR.md) | Designer, `.hasmeta`, export |
| [GUI_INTUITION_RUNTIME_SPEC.md](GUI_INTUITION_RUNTIME_SPEC.md) | Full HAS `Gui*` ABI |
| [GUI_PYTHONAMI_API.md](GUI_PYTHONAMI_API.md) | pythonami Layer 1 / Layer 2 |
| [GUI_LIBRARY.md](GUI_LIBRARY.md) | **Different** stack (bare-metal MsgBox/ComboBox) — not guicreator |

**Requires:** AmigaOS 2.0+ (`intuition.library` / `graphics.library` V37). Forms need
a real Amiga / AROS / WinUAE — Musashi has no Kickstart Intuition.

---

## 1. Quick start

### Design → code

```bash
.venv/bin/python3 -m guicreator
.venv/bin/python3 -m guicreator --export-has layout.hasmeta -o form.has
.venv/bin/python3 -m guicreator --export-python layout.hasmeta -o form.py
```

Put handler logic only between `USER CODE BEGIN` / `USER CODE END` markers so
re-export keeps it.

### Call order (both languages)

```text
init / GuiInit
  begin_window / GuiBeginWindow
    add_* / GuiAdd*
  show / GuiShow
    wait_event loop
  close_window / GuiCloseWindow
shutdown / GuiShutdown
```

One window per session. Add widgets **before** `show`. Max 32 gadgets + 32 labels.

### Event classes

| Constant | Value | Typical use |
| --- | ---: | --- |
| `GUI_EVT_CLOSE` | 1 | Close gadget |
| `GUI_EVT_BUTTON` | 2 | Button click |
| `GUI_EVT_STRING` | 4 | EditBox committed (Return / tab away) |
| `GUI_EVT_KEY` | 5 | Vanilla key (ASCII via `get_event_code` / `GuiGetEventCode`) |
| `GUI_EVT_CHECKBOX` | 8 | Checkbox toggled |
| `GUI_EVT_LIST` | 9 | List row selected |

Gadget **ActionID** (`gg_GadgetID`) ≥ 1 → `get_event_id()` / `GuiGetEventID()`.

---

## 2. Widget catalogue

| Type | Events | Read | Write / update |
| --- | --- | --- | --- |
| **Label** | none | — | HAS: `GuiSetLabelText`; pythonami: not exported today |
| **Button** | `BUTTON` | — (click is the signal) | HAS: `GuiEnableWidget` |
| **EditBox** | `STRING` | get text | set text; HAS: `GuiActivateEdit` |
| **CheckBox** | `CHECKBOX` | get 0/1 | no setter (user toggles) |
| **List** | `LIST` | selected row index | items fixed at `add_*` — **no runtime add/remove** |
| **Bitmap** | none | — | display-only |

There is **no** slider, combo box, or modal MessageBox gadget in guicreator. For a
“dialog until OK/Cancel” pattern in pythonami, use Layer 2 `gui_dialog` (§8).

---

## 3. Label

Static text (`PrintIText`). No events.

### HAS

```has
call GuiAddLabel(ID_LBL, 12, 24, &lbl_text);

// Later (declare extern GuiSetLabelText):
call GuiSetLabelText(ID_LBL, &new_caption);
```

### pythonami

```python
gui.add_label(ID_LBL, 12, 24, "Name:")
# set_label_text is optional in the contract and not in the current plugin export table
```

---

## 4. Button

Bool gadget; complete click → `GUI_EVT_BUTTON`.

### HAS

```has
call GuiAddButton(ID_OK, 116, 64, 88, 18, &ok_caption);

proc on_button(id: int) -> int {
    if (id == ID_OK) {
        // handle click — return 0 to leave the event loop
    }
    return 1;
}
```

### pythonami

```python
gui.add_button(ID_OK, 116, 64, 88, 18, "OK")

def on_button(gui, eid):
    if eid == ID_OK:
        pass  # handle click
    return 1
```

---

## 5. EditBox

String gadget. Text is stable after `GUI_EVT_STRING` (Return or tab away).
`maxlen` **includes** the terminating NUL.

### HAS — buffers in `bss`

```has
call GuiAddEditBox(ID_EDIT, 92, 22, 200, 14,
                   &edit_buf, &edit_undo, 32);

// Read (pointer to buffer):
text_ptr = GuiGetEditText(ID_EDIT);

// Write (NUL-terminated source string):
call GuiSetEditText(ID_EDIT, &preset);
call GuiActivateEdit(ID_EDIT);   // focus cursor
```

```has
bss buffers:
    edit_buf.b: 32
    edit_undo.b: 32
```

### pythonami — plugin owns buffers

```python
gui.add_editbox(ID_EDIT, 92, 22, 200, 14, "", 32)

# after GUI_EVT_STRING:
text = gui.get_edit_text(ID_EDIT)

gui.set_edit_text(ID_EDIT, "hello")
```

---

## 6. CheckBox

Toggle-select bool gadget. Initial `checked` nonzero = selected.

### HAS

```has
call GuiAddCheckBox(ID_CHK, 12, 44, 80, 14, &chk_caption, 0);

proc on_checkbox(id: int) -> int {
    if (id == ID_CHK) {
        checked = GuiGetCheckBox(ID_CHK);  // 1 or 0
    }
    return 1;
}
```

### pythonami

```python
gui.add_checkbox(ID_CHK, 12, 44, 80, 14, "Remember me", 0)

# after GUI_EVT_CHECKBOX:
checked = gui.get_checkbox(ID_CHK)
```

No dedicated setter — the user toggles via the gadget.

---

## 7. List

Fixed-height, **single-select**, Topaz-8 rows. **Not** a scrolling ListView.
Height must fit all rows: `count ≤ (h - 4) // 8`.

Items are supplied **once** at `add_*`. There is **no** API to add or remove
rows at runtime — change the layout / rebuild the form.

### HAS — pointer table + strings

```has
call GuiAddList(ID_LIST, 12, 62, 74, 40, &list_items, 3, 0);
// selected arg = initial row (0-based)

proc on_list(id: int) -> int {
    if (id == ID_LIST) {
        row = GuiGetListSelected(ID_LIST);  // or -1 if not a list
    }
    return 1;
}
```

```has
asm {
list_items:
    dc.l item0, item1, item2
}
data strings:
    item0.b = "Item 1", 0
    item1.b = "Item 2", 0
    item2.b = "Item 3", 0
```

### pythonami

```python
ITEMS = ["Item 1", "Item 2", "Item 3"]
gui.add_list(ID_LIST, 12, 62, 74, 40, ITEMS, 0)

# after GUI_EVT_LIST:
row = gui.get_list_selected(ID_LIST)
```

Designer: set items as `|`-separated text in the List properties panel.

---

## 8. Bitmap

Display-only image gadget (`GFLG_GADGIMAGE`). Clicks produce **no** handler.
HAS export needs **Pillow**; pixel planes go in `data_chip`.

### HAS

```has
call GuiAddBitmap(ID_BMP, 130, 48, 64, 64, &bmp_image);
// &bmp_image is a graphics/Image header; planes in data_chip
```

### pythonami

```python
rc = gui.add_bitmap(ID_BMP, 130, 48, 64, 64, "PROGDIR:icon.png")
# may return -1 if unsupported in a given plugin build
```

---

## 9. “Message box” / modal dialog

Guicreator has **no** MessageBox control.

| Need | Use |
| --- | --- |
| pythonami: block until OK / close, snapshot fields | Layer 2 `gui_dialog` |
| Bare-metal drawn MsgBox (not Intuition forms) | [GUI_LIBRARY.md](GUI_LIBRARY.md) / `lib/gui.s` — separate API |

### pythonami Layer 2

```python
import sys
sys.path.append("lib")
import gui_dialog

# after gui.show():
result = gui_dialog.run_modal_fields(gui, [
    ["edit", ID_EDIT],
    ["check", ID_CHK],
    ["list", ID_LIST],
])
# result["ok"]      — False on close gadget, True on any button
# result["button"]  — ActionID of the button, or 0
# result["fields"]  — { id: value, ... }
```

HAS forms use the generated `event_loop` and return `0` from a button/close
handler to dismiss — there is no separate MsgBox helper in `gui_intuition`.

---

## 10. Minimal event loops

### HAS (pattern from `examples/testgui.has`)

```has
while (running != 0) {
    evt = GuiWaitEvent();
    id = GuiGetEventID();
    if (evt == GUI_EVT_CLOSE)   { running = on_close(); }
    if (evt == GUI_EVT_BUTTON)  { running = on_button(id); }
    if (evt == GUI_EVT_STRING)  { running = on_string(id); }
    if (evt == GUI_EVT_CHECKBOX){ running = on_checkbox(id); }
    if (evt == GUI_EVT_LIST)    { running = on_list(id); }
}
```

### pythonami (pattern from `examples/gui_login_form.py`)

```python
while running != 0:
    evt = gui.wait_event()
    eid = gui.get_event_id()
    if evt == GUI_EVT_CLOSE:
        running = on_close(gui)
    if evt == GUI_EVT_BUTTON:
        running = on_button(gui, eid)
    if evt == GUI_EVT_STRING:
        running = on_string(gui, eid)
    if evt == GUI_EVT_CHECKBOX:
        running = on_checkbox(gui, eid)
    if evt == GUI_EVT_LIST:
        running = on_list(gui, eid)
```

Handlers return `1` to keep looping, `0` to exit.

---

## 11. API cheat sheet

### HAS (`lib/gui_intuition.s`)

| Call | Purpose |
| --- | --- |
| `GuiAddLabel` / `GuiAddButton` / `GuiAddEditBox` / `GuiAddCheckBox` / `GuiAddList` / `GuiAddBitmap` | Construct |
| `GuiGetEditText` / `GuiSetEditText` / `GuiActivateEdit` | EditBox |
| `GuiGetCheckBox` | CheckBox |
| `GuiGetListSelected` | List |
| `GuiSetLabelText` | Label update |
| `GuiEnableWidget` | Enable/disable gadget |
| `GuiWaitEvent` / `GuiGetEventID` / `GuiGetEventCode` | Events |

### pythonami plugin (current exports)

Lifecycle + `add_*` + event getters + `get_edit_text` / `set_edit_text` /
`get_checkbox` / `get_list_selected`.

**Not** in the current export table: `set_label_text`, `enable_widget`,
`activate_edit`, `redraw` (listed as optional in [GUI_PYTHONAMI_API.md](GUI_PYTHONAMI_API.md)).

---

## 12. Worked examples in the tree

| Example | Gadgets |
| --- | --- |
| [`examples/gui_login_form.has`](../examples/gui_login_form.has) / [`.py`](../examples/gui_login_form.py) | Label, EditBox, Button |
| [`examples/testgui.has`](../examples/testgui.has) | All six types |
| [`guicreator/examples/login.hasmeta`](../guicreator/examples/login.hasmeta) | Designer source for login |
| pythonami [`examples/gui_form.py`](../../pythonami/examples/gui_form.py) | Label, EditBox, Button, List + `gui_dialog` import |

Build HAS forms with `gui_intuition.s` + `wbstartup.s` (see [GUI_CREATOR.md](GUI_CREATOR.md)).
Run pythonami forms with `PROGDIR:ext/gui_intuition/gui_intuition.py68k` present.

---

## 13. Limitations (do not fight the runtime)

- Single window; static 32+32 pools; no `AllocMem` for gadgets.
- No overlapping controls (hit-test = first list match).
- List: no scroll, no multiselect, no runtime item mutation.
- Bitmap: Workbench pens, not a private palette; chip RAM for plane data.
- pythonami: top-level `def` only; keep each call on **one physical line**.
