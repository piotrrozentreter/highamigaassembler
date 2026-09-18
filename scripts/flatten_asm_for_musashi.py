#!/usr/bin/env python3
"""Rewrite multi-section HAS assembly into one code section for Musashi -Fbin.

vasm -Fbin rejects overlapping SECTION bases (DATA/BSS/CODE all default to 0).
Musashi's flat loader also requires the entry point at the start of the image,
so CODE must come first and DATA/BSS bodies are appended in the same section.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SECTION_RE = re.compile(r"^\s*SECTION\b", re.IGNORECASE)


def flatten(text: str) -> str:
    lines = text.splitlines(True)
    header: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current_kind: str | None = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_kind, current_body
        if current_kind is not None:
            sections.append((current_kind, current_body))
        current_kind = None
        current_body = []

    for line in lines:
        if SECTION_RE.match(line):
            flush()
            lower = line.lower()
            if ",code" in lower or ",code_" in lower:
                kind = "code"
            elif ",data" in lower or ",data_" in lower:
                kind = "data"
            elif ",bss" in lower or ",bss_" in lower:
                kind = "bss"
            else:
                kind = "other"
            current_kind = kind
            current_body = [line]
        elif current_kind is None:
            header.append(line)
        else:
            current_body.append(line)
    flush()

    code = [body for kind, body in sections if kind == "code"]
    rest = [body for kind, body in sections if kind != "code"]

    if not code:
        return text  # nothing to do

    if not rest and len(code) == 1:
        return text

    out: list[str] = list(header)
    # Keep the first code SECTION directive; append everything else under it.
    first = True
    for body in code:
        if first:
            out.extend(body)
            first = False
        else:
            # Drop subsequent SECTION lines; keep the content.
            out.append("\n; --- additional code section (flattened) ---\n")
            out.extend(body[1:] if body and SECTION_RE.match(body[0]) else body)

    for body in rest:
        out.append("\n; --- data/bss appended for flat Musashi binary ---\n")
        out.extend(body[1:] if body and SECTION_RE.match(body[0]) else body)

    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()
    src = Path(args.input).read_text(encoding="utf-8")
    Path(args.output).write_text(flatten(src), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
