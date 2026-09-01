# guicreator

WYSIWYG GUI designer for Amiga forms. Emits **structured metadata**, not an application:

- `.hasmeta` — layout pseudo-code for the HAS/68000 pipeline (also the project format)
- `.has` — a compilable `intuition.library` program skeleton with empty event handlers

Full documentation: [docs/GUI_CREATOR.md](../docs/GUI_CREATOR.md)
Runtime contract for the assembly side: [docs/GUI_INTUITION_RUNTIME_SPEC.md](../docs/GUI_INTUITION_RUNTIME_SPEC.md)

## Quick start

```bash
python -m guicreator                                   # designer
python -m guicreator guicreator/examples/login.hasmeta # designer, layout loaded
python -m guicreator --validate guicreator/examples/login.hasmeta
python -m guicreator --export-has guicreator/examples/login.hasmeta -o examples/gui_login_form.has
python -m hasc.cli examples/gui_login_form.has -o build/gui_login_form.s
```

Requires Python 3.8+ and Tkinter (bundled with CPython on Windows and macOS; on Debian/Ubuntu
`apt install python3-tk`). The headless `--validate` / `--export-has` paths do not import Tkinter.

## Modules

| Module | Role | Tkinter? |
| --- | --- | --- |
| `model.py` | `MetadataManager`, `WindowSpec`, `Control`, validation, ActionID counter | no |
| `hasmeta.py` | `.hasmeta` writer + reader (exact round-trip) | no |
| `has_export.py` | `.has` skeleton emitter, USER CODE preservation | no |
| `builder.py` | WYSIWYG designer | yes |
| `__main__.py` | CLI entry point | only for the UI path |

## Regeneration is safe

Re-exporting over an existing `.has` keeps everything you wrote between
`// USER CODE BEGIN <key>` and `// USER CODE END <key>`. Everything else is overwritten.
