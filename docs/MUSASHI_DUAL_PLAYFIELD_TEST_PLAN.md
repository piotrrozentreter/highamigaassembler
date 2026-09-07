# Musashi Runtime Test Plan: Dual Playfield (Mode 3)

**Audience:** an agent working on Linux (or WSL), picking up Musashi runtime
verification for graphics mode 3 that was postponed on a Windows dev machine.

Read `docs/MUSASHI_RUNTIME_TESTING.md` and `docs/MUSASHI_USER_GUIDE.md` first -
this document only adds mode-3-specific test content on top of that existing
tier. Do not re-explain or re-implement the Musashi setup/build/run scripts;
they already work, just add new `.has` fixtures and manifest entries.

## Scope and honest limitations

Musashi emulates the 68000 CPU only (per `MUSASHI_RUNTIME_TESTING.md`'s own
"Non-goal: full AmigaOS or chipset emulation"). It cannot render bitplanes to
a screen, so it **cannot visually confirm** that Playfield 1 and Playfield 2
actually composite correctly on real Denise/Agnes hardware. What it *can*
verify cheaply and repeatably is the **CPU-side correctness** of the runtime
library: did `SetGraphicsMode(3)` compute and write the values this feature
was designed to write, did `SetActivePlayfield`/`SetPixel`/`ClearScreen`/
`SwapScreen`/`ClearPlayfield` touch the right memory addresses, does
`Scroll` and `CreateBob`/`PasteBob`/`MirrorBobHorizontally`/
`MirrorBobVertically` correctly target only whichever playfield
`SetActivePlayfield` last selected, and does the one function that remains
deliberately unsupported in mode 3 (`BLITLINE`) really return `-1` instead
of corrupting memory.

Before writing register-readback assertions, inspect
`tools/musashi_runner/has_musashi_runner.c` to confirm how (or whether) the
runner models the `$DFF000` custom-chip address space. If custom-chip writes
are just treated as plain RAM by the runner (no real Denise/Agnes/Copper
side effects), a "read back BPLCON0" test only proves the CPU wrote the
value the code intended - which is still useful and is exactly what these
tests are for - but do not describe it in commit messages/docs as hardware
validation. Real hardware/emulator (WinUAE, FS-UAE, or real Amiga) visual
confirmation is a separate, still-open follow-up beyond this test tier.

## Background: what was implemented (read the code, this is a summary only)

- `lib/graphics.s`: `SetGraphicsMode(3)` configures a classic OCS/ECS 320x256
  dual-playfield mode - 6 line-interleaved bitplanes (40 bytes/plane/row),
  split by hardware into Playfield 1 (bitplanes 1,3,5) and Playfield 2
  (bitplanes 2,4,6), each with 7 visible colors + transparent. BPLCON0 value
  used: `%0110011000000000` (6 planes, DBLPF set, HAM off, COLOR_ON set).
  BPL1MOD/BPL2MOD = 200. New chip-RAM buffers `gfx_screen1_dualpf` /
  `gfx_screen2_dualpf` (320*256/8*6 = 61440 bytes each), guarded by a new
  `DISABLE_DUALPF` assembly-time flag mirroring `DISABLE_320x256`/
  `DISABLE_640x256`/`DISABLE_HAM`.
- New `SetActivePlayfield(playfield: int) -> int` (1 or 2) selects which
  physical bitplane group (`gfx_active_playfield`, a word variable) later
  drawing calls target. Only valid in mode 3.
- `_gfx_can_plot`, `_SetPixel`, `_DrawChar` (used by `Text`/`Print`),
  `gfx_clear_screen`, `SwapScreen`, `Show`/`UpdateCopperList`, `SetColor`,
  `LoadPalette` all gained mode-3-aware branches.
- `BLITLINE` explicitly rejects mode 3 (returns `-1`) - its line-mode geometry
  table has no dual-playfield entry. `Scroll` and `CreateBob`/`PasteBob`/
  `MirrorBobHorizontally`/`MirrorBobVertically` (`lib/bob.s`) now work in mode 3
  instead, targeting whichever playfield `SetActivePlayfield` last selected.
  New `ClearPlayfield(playfield: int) -> int` clears only one playfield's 3
  owned bitplanes without resetting the text cursor. A pre-existing bug where
  BOB functions silently mistreated HAM6 (mode 2) as hires was fixed at the
  same time - they now explicitly reject HAM6 instead.
- Working example: `examples/dual_playfield_demo.has` (compiles, assembles,
  and links cleanly for both `--cpu 68000` and `--cpu 68020`; not yet run on
  an emulator/hardware with real video output).
- A prior code-review pass (same feature, same day) found and fixed two
  blocking register-clobber/out-of-bounds bugs and one high-severity bug
  before this was considered mergeable - see `docs/CHANGELOG.md`'s dual
  playfield entry and the git history for `lib/graphics.s` around this
  feature for exact before/after context if something looks suspicious.

## Recommended new runtime tests

Add these under `examples/runtime_musashi/` and register them in
`tests/runtime_musashi_manifest.txt`, following the MMIO PASS/FAIL protocol
documented in `MUSASHI_RUNTIME_TESTING.md` (`0x00100004` = PASS,
`0x00100000` = FAIL, `0x00100014` = debug byte). Use `extern var` memory
peeks the same way the existing codebase already does for this class of
diagnostic (see the `gfx_current_screen_ptr`/`Scroll()` bug writeup in this
repo's engineering history for the exact pattern: declare
`extern var <symbol>: byte*;` or similar, index into it, and branch to
PASS/FAIL based on the observed byte).

1. **`dualpf_mode_select_test.has`** - call `SetGraphicsMode(3)`, assert the
   return value is `0`, then peek `gfx_current_mode` and assert it reads `3`.
   Also call `SetGraphicsMode(99)` (invalid) first and assert it returns
   `-1` and leaves the mode unchanged, to confirm the raised bound check
   (`cmp.l #3,d1` / `bgt .error`) is correct at the boundary.

2. **`dualpf_active_playfield_test.has`** - after `SetGraphicsMode(3)`:
   assert `SetActivePlayfield(1)` and `SetActivePlayfield(2)` both return
   `0`; assert `SetActivePlayfield(0)` and `SetActivePlayfield(3)` both
   return `-1`; assert calling `SetActivePlayfield(1)` while in mode 0
   (after a subsequent `SetGraphicsMode(0)`) returns `-1`.

3. **`dualpf_pixel_plane_routing_test.has`** - the most important test:
   after `SetGraphicsMode(3)`, `SetActivePlayfield(1)`, call
   `SetPixel(0, 0, 1)` (color code 1 - bit 0 only). Peek the first byte of
   `gfx_screen1_dualpf` (physical plane slot 0 = bitplane 1) and assert bit 7
   is set, while the byte 40 bytes later (physical plane slot 1 = bitplane 2,
   which belongs to Playfield 2) is still 0. Then `SetActivePlayfield(2)`,
   `SetPixel(0, 0, 1)` again, and assert the OPPOSITE: the byte at slot 1
   (offset 40) now has bit 7 set, and slot 0 is unaffected by this second
   call. This directly exercises the physical-plane-slot / color-bit-index
   split fixed during code review (`_SetPixel`'s `.sp_dualpf` branch) and is
   the single highest-value test to add, since it is exactly the class of
   bug (silent wrong-address writes) that historically was NOT caught by
   compile/assemble/link checks alone in this codebase.

4. **`dualpf_clearscreen_test.has`** - write a few non-zero test bytes into
   `gfx_screen1_dualpf` via `SetPixel` calls on both playfields, call
   `ClearScreen()`, then peek several offsets across the 61440-byte buffer
   (start, middle, end) and assert all are zero - confirms the blitter
   `BLTSIZE=480<<6` clear covers the whole buffer with the correct
   height/width factorization.

5. **`dualpf_swapscreen_test.has`** - after `SetGraphicsMode(3)`, peek
   `gfx_current_screen_ptr` and assert it equals the address of
   `gfx_screen1_dualpf` (needs `extern var gfx_screen1_dualpf: byte*;` or an
   equivalent way to get its address - check whether `lib/graphics.s`
   exports it via `XDEF`; if not, compare by writing a known pattern via
   `SetPixel` before `SwapScreen()` and confirming the pattern is NOT visible
   through `gfx_current_screen_ptr` immediately after the swap, since it
   should now point at the other buffer). Call `SwapScreen()` once and
   assert the pointer changed to the other dual-playfield buffer, not to
   `gfx_screen1`/`gfx_screen2` (the lores buffers) - this is the exact bug
   class fixed in `SwapScreen` during this feature's code review.

6. **`dualpf_rejected_apis_test.has`** - after `SetGraphicsMode(3)`, assert
   `BLITLINE(0, 0, 63, 63, 1)` returns `-1` (its line-mode geometry table has
   no dual-playfield entry - this restriction is unchanged). The call should
   not hang, crash, or corrupt memory - assert a few bytes of
   `gfx_screen1_dualpf` before/after the call are unchanged as a cheap
   corruption smoke check. `Scroll` and `CreateBob` are no longer rejected in
   mode 3 (see the positive tests below) and must NOT be asserted to return
   `-1` here.

7. **`dualpf_scroll_test.has`** - after `SetGraphicsMode(3)`, use
   `SetActivePlayfield(1)` + `SetPixel` to draw a known pattern into
   Playfield 1's owned bytes, then `SetActivePlayfield(2)` and draw a
   different pattern into Playfield 2. Call `Scroll(...)` while Playfield 1
   is active and assert: (a) it returns `0`; (b) Playfield 1's owned bytes
   moved as expected; (c) Playfield 2's owned bytes are completely
   untouched - the core "independent per-playfield scroll" guarantee, and
   the single highest-value assertion for this test. Also assert `Scroll`
   still returns `-1` in HAM6 (mode 2), unchanged.

8. **`dualpf_bob_test.has`** - after `SetGraphicsMode(3)` and
   `SetActivePlayfield(1)`, call `CreateBob(...)` with a small test
   descriptor and assert it returns a handle other than `-1`; `PasteBob` it
   at a known position and peek the affected bytes to confirm the paste
   landed only in Playfield 1's owned planes. Repeat with
   `SetActivePlayfield(2)` and assert the opposite. Also exercise
   `MirrorBobHorizontally`/`MirrorBobVertically` on the mode-3 handle and
   assert they return a valid new handle rather than `-1`. Finally, switch
   to `SetGraphicsMode(2)` (HAM6) and assert `CreateBob` returns `-1` there
   - the one restriction that did not change.

9. **`dualpf_clearplayfield_test.has`** - after `SetGraphicsMode(3)`, draw
   non-zero test bytes into both playfields via `SetPixel`, call
   `ClearPlayfield(1)`, and assert Playfield 1's bytes are zeroed while
   Playfield 2's are unchanged; repeat for `ClearPlayfield(2)` the other way
   round. Assert `ClearPlayfield(0)`/`ClearPlayfield(3)` (invalid playfield)
   and calling it outside mode 3 all return `-1` without touching memory.
   Also peek `gfx_text_cursor_x`/`gfx_text_cursor_y` before/after and assert
   they are unchanged, unlike `ClearScreen`.

## Procedure

1. `./scripts/setup_musashi.sh && ./scripts/build_musashi_runner.sh` (Linux
   prerequisites: git, python3, gcc, vasmm68k_mot in PATH - see
   `MUSASHI_USER_GUIDE.md`).
2. Write the nine `.has` files above under `examples/runtime_musashi/`,
   following the MMIO PASS/FAIL protocol and the exact style of existing
   files in that directory.
3. Add each new file's path to `tests/runtime_musashi_manifest.txt`.
4. `./scripts/test_runtime_musashi.sh` - expect `fail=0`.
5. `python3 -m pytest tests/test_runtime_musashi.py -v` as a secondary check.
6. Run the full non-Musashi regression sweep too
   (`.github/skills/regression-sweep/SKILL.md`, Tier 3) to confirm nothing
   else moved since this plan was written - `python3 -m pytest tests -q`
   should show 690 passed, 1 skipped as of this writing (confirm the current
   count hasn't drifted before treating any new failure as caused by this
   test plan's changes).
7. Update `docs/CHANGELOG.md` with a short note that mode 3 now has Musashi
   runtime coverage, and update this file's or `MUSASHI_RUNTIME_TESTING.md`'s
   test inventory if the actual filenames/assertions end up differing from
   the plan above.

## Still out of scope after this test tier

Real visual/compositing confirmation (does Playfield 2 actually appear in
front of Playfield 1 on screen, does color code 0 really show Playfield 1
through Playfield 2, does the palette mapping look right) requires an
Amiga emulator with real chipset/video emulation (WinUAE, FS-UAE) or real
hardware, not Musashi. Do that check separately, and update
`examples/dual_playfield_demo.has`'s header comment plus
`docs/GRAPHICS_LIBRARY_INTERFACE.md` once it's been visually confirmed at
least once.
