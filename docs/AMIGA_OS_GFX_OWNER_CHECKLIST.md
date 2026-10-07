# Owner-run checklist — Amiga OS Gfx API

Validate on AROS / WinUAE / hardware (not Musashi). Both repos on
`feature/amiga-os-gfx`.

## HAS

1. Build `examples/amiga_gfx_demo.has` per header comments → `build/amiga_gfx_demo.exe`
2. Run from Workbench or CLI; expect LORES screen with plot/line/rect/circle/text
3. Quit with ESC / q / close; returns cleanly to Workbench
4. Optional: rebuild with `--cpu 68020` and repeat

## pythonami

1. `export VBCC=…` if needed; `make -f Makefile.amiga amiga-ext`
2. Confirm `ext/amiga_gfx/amiga_gfx.py68k` exists
3. Host `--check`: `examples/amiga_gfx_smoke.py`, `test_amiga_gfx.py`,
   `test_amiga_gfx_blit_sprites.py`, `test_amiga_gfx_window.py`
4. Amiga: `test_amiga_gfx_blit_sprites.py` (8 sprites + blit + joy/mouse)
5. Amiga: `test_amiga_gfx_window.py` (normal WB window draw/blit)
6. Quit ESC/q/close; no guru

## Explicitly out of scope here

- Bare-metal `TakeSystem` / `lib/graphics.s` unchanged
- HAM / dual-playfield / AGA
- Host simulator for OpenScreen
