"""Command line entry point for the HAS GUI Creator.

    python -m guicreator                          # launch the WYSIWYG designer
    python -m guicreator form.hasmeta             # launch with a layout loaded
    python -m guicreator --export-has form.hasmeta -o gui_form.has
    python -m guicreator --export-python form.hasmeta -o gui_form.py
    python -m guicreator --validate form.hasmeta
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from . import has_export, hasmeta, py_export
from .model import MetadataManager


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m guicreator",
        description="WYSIWYG GUI designer emitting HAS metadata and pythonami skeletons.",
        epilog=(
            "Examples:\n"
            "  python -m guicreator\n"
            "  python -m guicreator guicreator/examples/login.hasmeta\n"
            "  python -m guicreator --export-has guicreator/examples/login.hasmeta "
            "-o examples/gui_login.has\n"
            "  python -m guicreator --export-python guicreator/examples/login.hasmeta "
            "-o examples/gui_login_form.py\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("layout", nargs="?", help=".hasmeta layout to load")
    parser.add_argument(
        "--export-has",
        metavar="LAYOUT",
        help="headless: read LAYOUT and write a .has skeleton, no GUI",
    )
    parser.add_argument(
        "--export-python",
        metavar="LAYOUT",
        help="headless: read LAYOUT and write a pythonami .py skeleton, no GUI",
    )
    parser.add_argument("-o", "--output", help="output path for --export-has / --export-python")
    parser.add_argument(
        "--validate", metavar="LAYOUT", help="headless: validate LAYOUT and report problems"
    )
    parser.add_argument(
        "--no-preserve",
        action="store_true",
        help="overwrite USER CODE blocks instead of carrying them over",
    )
    return parser.parse_args(argv)


def _validate(path: Path) -> int:
    manager = hasmeta.load(path)
    problems = manager.validate()
    if not problems:
        print(f"{path}: OK ({len(manager)} controls)")
        return 0
    print(f"{path}: {len(problems)} problem(s)", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


def _export_has(layout: Path, output: Optional[Path], preserve: bool) -> int:
    manager: MetadataManager = hasmeta.load(layout)
    problems = manager.validate()
    for problem in problems:
        print(f"warning: {problem}", file=sys.stderr)
    target = output or layout.with_suffix(".has")
    has_export.save(manager, target, meta_source=str(layout), preserve_user_code=preserve)
    print(target)
    return 0


def _export_python(layout: Path, output: Optional[Path], preserve: bool) -> int:
    manager: MetadataManager = hasmeta.load(layout)
    problems = manager.validate()
    for problem in problems:
        print(f"warning: {problem}", file=sys.stderr)
    target = output or layout.with_suffix(".py")
    py_export.save(manager, target, meta_source=str(layout), preserve_user_code=preserve)
    print(target)
    return 0


def main(argv=None) -> int:
    args = _parse_args(argv)

    if args.validate:
        return _validate(Path(args.validate))

    if args.export_has:
        return _export_has(
            Path(args.export_has),
            Path(args.output) if args.output else None,
            not args.no_preserve,
        )

    if args.export_python:
        return _export_python(
            Path(args.export_python),
            Path(args.output) if args.output else None,
            not args.no_preserve,
        )

    try:
        from .builder import GuiCreatorApp
    except ImportError as exc:
        print(f"Tkinter is required for the designer UI: {exc}", file=sys.stderr)
        return 2

    app = GuiCreatorApp()
    if args.layout:
        path = Path(args.layout)
        app.manager = hasmeta.load(path)
        app.project_path = path
        app.selected = None
        app._refresh_all()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
