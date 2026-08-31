---
description: "Use when editing asset-pipeline tools in tools/, including sprite/BOB/tile/atlas/IFF importers, font and frame converters, and any script that emits 68000 assembly data files."
applyTo:
  - "tools/**/*.py"
---

# HAS Asset Tooling Instructions

## Primary Goal

These are standalone CLI converters that turn source assets (PNG, IFF, C64 data, TexturePacker
atlases) into 68000 assembly data files consumed by `lib/*.s` and HAS programs. Correctness of the
emitted binary layout matters more than Python elegance - a wrong header word is invisible until it
crashes on real hardware.

## Emitted Assembly Conventions

- Directives are **UPPERCASE** in `tools/*.py` (`SECTION`, `XDEF`, `CNOP`, `EVEN`, `DC.W`), unlike
  `hasc/codegen.py` which emits lowercase. Match the surrounding file, do not normalize across the two.
- Every `SECTION` must be immediately followed by `CNOP<TAB>0,4`. This is a project-wide invariant;
  if you add a new `SECTION` emission site, add the `CNOP` too.
- Chip RAM (`DATA_C`) is **only** for data the custom chips must DMA from: bitplanes, BOB/sprite
  image and mask data, copper lists, and audio samples. Everything else - descriptors, offset
  tables, frame metadata, palettes consumed only by CPU code - belongs in plain `DATA`/`BSS`
  (fast RAM), which is faster for the CPU and far more plentiful.
  Chip RAM is a scarce resource; never widen a section to `DATA_C` for convenience.
  **If you cannot determine from the consumer whether a block is DMA'd, ask before choosing.**
- Respect 68000 even-address alignment: emit `EVEN` before any word/long data that could follow an
  odd number of bytes.

## Tab Escaping Trap

Most `tools/*.py` files write tab-indented directives using the literal two-character Python escape
`\t` inside strings (`f"\tSECTION bobs,DATA_C"`). **`tools/frame_merger.py` is the exception** - it
contains real tab bytes (0x09) typed directly into its string literals.

Before constructing an edit, confirm which convention the target line uses (a non-regex search for
the two-character sequence `\t` matches only the escape-sequence files). Mismatching the two makes
edits silently fail to match, or match the wrong line.

## Cross-Tool Coupling

`tools/frame_merger.py` re-parses **already-generated** `.s` files rather than regenerating from
source images. It strips each input's `SECTION`, `XDEF`, and `CNOP` lines to emit one consolidated
set. Whenever you add a new per-file prologue directive to any individual generator, check whether
`frame_merger.py`'s strip loop needs a matching skip rule - otherwise the new directive leaks
duplicated into merged output.

Several tools delegate rather than duplicating emission logic - e.g. `iff_importer.py`'s non-HAM6
path and `texturepacker_atlas_importer.py`'s main path both call into `bob_importer.py`. Fix shared
behavior at the shared function, not at each caller.

## Runtime Contract

Generated data is consumed by hand-written `lib/*.s` routines. When changing a data layout:

- Update the matching reader in `lib/` in the same change, and state the byte offset of every
  field you moved.
- Remember that HAS pushes `int` arguments as 32-bit longs and 68k is big-endian - a `lib/*.s`
  routine reading a small `int` param with `move.w 8(a6),d0` gets the always-zero high word. Use
  `move.l`. vasm will not catch this; it is a semantic bug.
- Header words written by a tool that cannot be reconstructed at runtime (e.g. `bob_importer.py`'s
  `--add-word` padding, which is indistinguishable from ordinary width) must not be re-derived by
  guesswork in the runtime library.

## Code Discipline

- Keep tools standalone and argparse-driven; do not import from `hasc/`.
- Pillow is an optional dependency - keep `from PIL import Image` inside a guarded import with a
  clear error message, matching the existing pattern.
- Never call `Image.getdata()` directly (removed in Pillow 14). Use `flatten_image_pixels()` from
  `bob_importer.py` / `sprite_importer.py`.
- Prefer localized edits.

## Verification Expectations

- Run the tools test suite: `python3 -m pytest tests/test_tools_*.py -q`. It covers planar bit
  packing, emitted assembly structure, the `SECTION` -> `CNOP 0,4` invariant, the chip-RAM
  allowlist, uppercase directives, and `frame_merger` prologue stripping.
- Add tests alongside any behavior change; `tests/tools_helpers.py` has PNG fixtures and assembly
  assertions.
- For layout changes, also run the tool on a real asset and inspect the emitted `.s` by eye, then
  assemble it: `vasmm68k_mot -m68000 -Fhunkexe -o /tmp/t.o generated.s`. Clean assembly proves
  syntax only - it does **not** prove the data layout is right.
- If the output feeds `frame_merger.py`, run the merge step too and inspect the merged file.
