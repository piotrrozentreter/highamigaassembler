# Pythonami GUI API (guicreator bridge)

**Audience:** guicreator exporters, pythonami extension authors, and form authors.
**Purpose:** stable contract for displaying and interacting with dialogs designed in
guicreator, under [pythonami](../../pythonami/) (Python68K) language semantics.

**Companion documents**

- [GUI_CREATOR.md](GUI_CREATOR.md) — designer and `.hasmeta` format
- [GUI_INTUITION_RUNTIME_SPEC.md](GUI_INTUITION_RUNTIME_SPEC.md) — HAS `Gui*` assembly runtime (behavioral reference)
- [GUI_GADGETS_GUIDE.md](GUI_GADGETS_GUIDE.md) — practical gadget usage with short examples
- pythonami: `docs/amiga-extensions.md`, `ext/gui_intuition/`, `lib/gui_dialog.py`

**Locked decisions**

- Layered API: low-level Gui*-mirror (Layer 1) + thin modal helper (Layer 2).
- Native backend is a new LoadSeg plugin in pythonami (`ext/gui_intuition/gui_intuition.py68k`).
  It does **not** link HAS `lib/gui_intuition.s`; that file remains the LVO/call-order reference.
- pythonami has no classes, no nested `def`/closures, and no Intuition in the VM core.

---

## Plugin path

```python
gui = load_library("PROGDIR:ext/gui_intuition/gui_intuition.py68k")
```

Keep the module reachable while calling exports (UnloadSeg runs on module destroy).

---

## Layer 1 — low-level (stable, extensible)

Snake_case mirror of the HAS `Gui*` surface. Numeric event codes and ActionIDs match
`.hasmeta` / HAS exactly.

### Lifecycle and construction

| Export | Args | Returns | Notes |
|--------|------|---------|-------|
| `init` | none | `int` | 0 = OK, -1 = failed. Opens intuition V37 + graphics. Idempotent. |
| `shutdown` | none | `None` | Close window if open, then libraries (reverse open order). |
| `begin_window` | `title: str, x, y, w, h, idcmp, flags` | `int` | Template only. 0 = OK, -1 = busy. |
| `add_label` | `id, x, y, text: str` | `int` | Static IntuiText; no events. |
| `add_button` | `id, x, y, w, h, caption: str` | `int` | Bool gadget, RELVERIFY. |
| `add_editbox` | `id, x, y, w, h, initial: str, maxlen` | `int` | Plugin owns buffers. `maxlen` includes NUL. |
| `add_checkbox` | `id, x, y, w, h, caption: str, checked` | `int` | Nonzero `checked` selects initially. |
| `add_list` | `id, x, y, w, h, items: list, selected` | `int` | `items` is a list of `str`. Single-select, no scroll. |
| `add_bitmap` | `id, x, y, w, h, path: str` | `int` | Optional; may return -1 if unsupported in an early build. |
| `show` | none | `int` | Window pointer as int, or 0 / -1 on failure. |
| `close_window` | none | `None` | Idempotent. |

### Event loop

| Export | Returns | Notes |
|--------|---------|-------|
| `wait_event` | `int` | Blocks; returns `GUI_EVT_*`. |
| `get_event_id` | `int` | Last gadget ActionID, or 0. |
| `get_event_code` | `int` | ASCII for `GUI_EVT_KEY`. |
| `get_event_x` / `get_event_y` | `int` | Last mouse coords. |

### Widget access

| Export | Returns | Notes |
|--------|---------|-------|
| `get_edit_text` | `str` | Empty string if unknown id. |
| `set_edit_text` | `int` | `text: str`; 0 = OK, -1 = fail. |
| `get_checkbox` | `int` | 1 selected, 0 clear/missing. |
| `get_list_selected` | `int` | Zero-based row, or -1. |
| `set_label_text` | `int` | Optional; may be stubbed until needed. |
| `enable_widget` | `int` | Optional. |
| `activate_edit` | `int` | Optional. |
| `redraw` | `None` | Optional. |

### Event constants (must match HAS)

| Name | Value |
|------|-------|
| `GUI_EVT_NONE` | 0 |
| `GUI_EVT_CLOSE` | 1 |
| `GUI_EVT_BUTTON` | 2 |
| `GUI_EVT_PRESS` | 3 |
| `GUI_EVT_STRING` | 4 |
| `GUI_EVT_KEY` | 5 |
| `GUI_EVT_MOUSE` | 6 |
| `GUI_EVT_REFRESH` | 7 |
| `GUI_EVT_CHECKBOX` | 8 |
| `GUI_EVT_LIST` | 9 |

### Mandatory call order

```text
init()
  begin_window(...)
    add_* (...)
  show()
    loop: wait_event() / getters
  close_window()
shutdown()
```

Single-window session only (HAS parity). Multi-window is a future ABI bump.

### Extensibility

- New widgets = new `add_*` + event class + getters; never recycle ActionIDs.
- Keep Layer 1 names stable; add optional exports rather than overloading arity.

---

## Layer 2 — modal helper

Pure Python module `gui_dialog` (shipped under pythonami `lib/gui_dialog.py`):

```python
import sys
sys.path.append("lib")
import gui_dialog

# After gui.show() succeeded:
result = gui_dialog.run_modal(gui)
```

Semantics:

1. Loop `wait_event`.
2. On `GUI_EVT_CLOSE` → snapshot fields, `close_window`, return `ok=False`.
3. On `GUI_EVT_BUTTON` → snapshot fields, `close_window`, return `ok=True`, `button=id`.
4. Other events are ignored (or may call optional hooks later).

Scripts that need custom logic use Layer 1 only (generated event loop + USER CODE hooks).

---

## guicreator export

```bash
.venv/bin/python3 -m guicreator --export-python layout.hasmeta -o form.py
```

Generated Python:

- Uses `load_library` + Layer 1.
- Top-level `def` only (no classes).
- Keep every call on **one physical line** (pythonami often rejects
  newlines inside parentheses in assignments — error looks like
  `expected else in conditional expression`).
- Preserves `# USER CODE BEGIN <key>` / `# USER CODE END <key>` on re-export
  (same keys as HAS: `form.externs`, `main.after_show`, `{name}.on_click`, …).

---

## Extension ABI note (pythonami)

Owned `str` / `list` results from plugins require `Py68ExtServices` on the runtime
(see pythonami `include/py68k_ext.h` and D-0048). Plugins must not link the
interpreter or `amiga.lib`.

---

## Validation

| Gate | Evidence |
|------|----------|
| Host guicreator tests | pytest `tests/test_guicreator.py` |
| pythonami host suite | `make -f Makefile.host test` after ABI changes |
| Plugin compile/link | `make amiga-ext` (vbcc) |
| Intuition execution | Owner on AROS / WinUAE / hardware — not Musashi (no Kickstart) |
