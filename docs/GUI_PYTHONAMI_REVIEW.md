# Review notes — guicreator ↔ pythonami GUI bridge (2026-09-23)

## HAS / guicreator

- `py_export` mirrors HAS USER CODE keys and event constants; ActionIDs unchanged.
- Headless `--export-python` does not import Tkinter.
- `examples/gui_login_form.py` is regenerable from `login.hasmeta` (pytest lock).
- API doc is the cross-repo contract; HAS `gui_intuition.s` remains behavioral reference only.

## pythonami

- D-0048: `ext_services` is first field of `Py68Runtime`; plugins use `Py68ExtRuntimeHead`.
- Plugin does not link `amiga.lib` / `vc.lib`; local string helpers; SysBase from `*(4)`.
- Bitmap `add_bitmap` returns -1 (API-stable stub).
- List display is caption-collapsed (not full HAS row gadgets); selection by mouse Y / 8.
- `list_get_copy` results released via `value_release` in `add_list`.

## Evidence

| Check | Result |
|-------|--------|
| HAS `pytest tests/test_guicreator.py` | 35 passed |
| Host `test_ext_services` | OK |
| `make amiga-ext` (demo_add + gui_intuition) | link OK |
| Intuition on Kickstart / Musashi | not run — owner Amiga/AROS; Musashi has no Intuition |

## Residual risks

- Plugin `(void)argc` warnings under vbcc (harmless).
- Edit/list string pools are fixed-size; long captions truncate.
- Multi-window not supported (documented).
