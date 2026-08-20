# Changelog

All notable changes to the HAS (High Assembler) project will be documented in this file.

## [Unreleased]

### Added

- **Configurable heap buffer size** in `lib/heap.s` and `scripts/build_game.sh`:
  - The heap now defaults to `10*1024` bytes instead of the previous roughly 138 KiB
    reservation. Pass `-D HEAP_MEMORY=<bytes>` to vasm for a direct heap assembly, or set
    `HEAP_MEMORY=<bytes>` when using `scripts/build_game.sh`; the build helper applies the
    define only to `lib/heap.s`.
  - The heap remains in `bss_c` and therefore consumes CHIP RAM. Keep overrides at or below
    roughly 128 KiB because block lengths are stored as 16-bit word counts. A `141312`-byte
    (138 KiB) override is not allocator-safe until the heap metadata is redesigned, so Jetpac
    should not enable that size yet.

- **Opt-in memory savings for unused graphics modes** in `lib/graphics.s`:
  - Three new assembly-time defines - `DISABLE_320x256`, `DISABLE_640x256`,
    `DISABLE_HAM` - let apps that only use a subset of the three supported
    graphics modes (lores 320x256x32, hires 640x256x16, HAM6 320x256) skip
    reserving the corresponding chip-RAM screen buffer(s), e.g.:
    `vasmm68k_mot -Fhunk -D DISABLE_640x256=1 -D DISABLE_HAM=1 -o graphics.o lib/graphics.s`
    saves ~225,280 of the baseline 327,680 bytes reserved by the `screen`
    section when only lores mode is used. Any combination of the three may be
    defined.
  - The same flags also omit the corresponding mode-specific copper list,
    including its palette and pointer entries, while retaining all copper-list
    labels for assembly and linking compatibility.
  - The buffer labels always stay defined regardless of which defines are
    set, so unrelated code in `graphics.s` still assembles/links; a disabled
    buffer shrinks to a 2-byte placeholder rather than 0 bytes, since an
    entirely empty `bss_c` `screen` section previously crashed `vlink`
    (V0.17a) with an access violation.
  - `SetGraphicsMode()` now refuses to activate a mode whose buffer was
    disabled at assembly time, returning its existing `d0 = -1` error code
    instead of running against the shrunk placeholder buffer. Callers must
    still check the return value (or avoid calling a disabled mode).
  - See [docs/GRAPHICS_LIBRARY_INTERFACE.md](GRAPHICS_LIBRARY_INTERFACE.md#opt-in-memory-savings-disabling-unused-screen-buffers-and-copper-lists).

## [0.9.5] - 2026-08-19

### Fixed

- **Signed byte/word global and extern variables are now sign-extended on load**:
  - Previously, loading a `data`/`bss` section global or an `extern var` byte
    or word into a register always zero-extended it (`andi.l #$FF`/`#$FFFF`),
    regardless of its declared signedness - so a negative value like `-3`
    (`0xFD`) would read back as `253`, silently breaking comparisons/arithmetic
    that depended on the sign (e.g. `if (dx < 0)`).
  - `extern var name: i8;` / `word`/`i16`-typed extern declarations now
    correctly emit `extb.l` (on `--cpu 68020`) or `ext.w`+`ext.l` (on
    `--cpu 68000`) instead of zero-extending.
  - Added an opt-in typed global declaration syntax for `data`/`bss` sections,
    `name: i8 = value;` (also `byte`/`i16`/`word`/etc.), which sign-extends on
    load. The legacy `name.b = value;` / `name.w = value;` suffix syntax is
    unchanged and still zero-extends (existing examples compile to identical
    assembly).
  - See `examples/global_signed_byte_test.has`, `examples/extern_signed_byte_test.has`,
    and `examples/games/signed_global_velocity_demo.has`.

- **`MirrorBobHorizontally` no longer requires `--add-word`** in `lib/bob.s`:
  - Previously always subtracted 16px from the source data-header width,
    assuming every BOB was built with the `--add-word` blitter-scroll padding
    option. For BOBs built without `--add-word` (the common case), this
    underflowed the visible-span calculation and made the call fail
    (return `-1`) for any handle whose stored width was `<= 16`, and produced
    a horizontally-truncated mirror for wider ones.
  - Fixed to bit-reverse the entire stored row (all chunks) instead of
    assuming a trailing 16px scroll chunk, so the function now works
    regardless of whether the source BOB used `--add-word`.
  - `examples/tests/compiler/bob_mirror_format_test.has` rewritten with a
    plain (non-`--add-word`) fixture and hand-verified expected mirrored
    values; `examples/tests/compiler/bob_mirror_api_test.has` now exercises
    the previously-broken 16px-wide case successfully.

### Changed

- **RNG bounded-value generation fixed** in `lib/helpers.s`:
  - Corrected rejection-mask construction so `RndMaxAMOS()` remains efficient
    and uniform for ordinary bounds such as `2`, `3`, `100`, and `256`.
  - Invalid bounds now return `0`, including values outside the 24-bit source
    domain; `max == 0x1000000` remains valid.
  - `SeedRnd()` now explicitly returns `0` in `d0`, matching its documented
    `void` contract.
- **RNG runtime contract documented** in `docs/LIBRARY_REFERENCE.md`:
  - `RndMaxAMOS(max)` uses half-open bounds `[0, max)` and returns `0` for
    `max <= 1` or `max > 0x1000000`; `max == 0x1000000` is valid.
  - `Rnd()` and `RndAMOS()` return raw 24-bit LCG output (`0..0xFFFFFF`).
  - `SeedRnd()` is deterministic for repeatable sequences, and the RNG is not
    suitable for security or cryptographic use.

### Added


- **Opt-in Motorola 68020 target completed**:
  - Added `--cpu {68000,68020}`, with `68000` remaining the default. The default
    output and explicit `--cpu 68000` output remain byte-for-byte identical.
  - Centralized indexed-address lowering now serves primitive 1D reads/stores,
    typed-pointer reads/stores, struct-array member reads/stores, two-dimensional
    reads/stores, and address-of operations.
  - Under `--cpu 68020`, legal `.l` scaled operands use `*2`, `*4`, or `*8` for
    supported element/struct strides. Legal struct field displacements can be
    folded into the same operand; larger or unsupported displacements retain
    explicit arithmetic.
  - Arbitrary strides retain `mulu.w` when representable; strides above the
    16-bit multiply range use full-width shift/add lowering. Constant indexes
    remain direct offsets, and byte indexing remains unscaled.
  - Matching assembler selection is required: use `-m68000` for baseline output
    and `-m68020` for scaled output. Memory-indirect, `.w` index, and unrelated
    68020 instruction optimizations remain deferred.

- **Full-extension indexed addressing for `--cpu 68020`** (Phase 1 of
  `docs/CPU_68020_IMPLEMENTATION_PLAN.md`):
  - `lower_indexed_address()` now emits scaled indexed operands with
    displacements outside the previous -128..127 "brief" range (e.g.
    `1000(a0,d1.l*4)`) when the target CPU supports full-extension addressing,
    instead of raising an error or falling back to explicit shift/add
    arithmetic. `TargetSpec.for_cpu(M68020)` sets
    `supports_full_index_extension=True`; `--cpu 68000` is unaffected and
    continues to reject out-of-range displacements the same way as before.
  - Applies to dynamic array/pointer indexing and struct-array field access
    in `hasc/codegen_indexed_address.py`. The `--cpu 68000` default output
    path is unchanged (verified byte-identical against prior committed output).
  - Reachable today for dynamic array/pointer indexing with large per-element
    strides; see `examples/cpu68020_dynamic_large_index.has`. Struct-array
    field access also folds into this path, but scaled struct addressing is
    only enabled when a struct's total size is exactly 2, 4, or 8 bytes, so no
    real HAS struct layout can currently exceed the brief-range displacement
    for that case (see `examples/cpu68020_struct_array_indexing.has`); the
    out-of-range struct-field path is covered only by direct unit tests of the
    lowering helper.

- **`.w` index selection via conservative range analysis for `--cpu 68020`**
  (Phase 2 of `docs/CPU_68020_IMPLEMENTATION_PLAN.md`):
  - Added `index_fits_word_range()` in `hasc/indexed_address.py`, which
    returns `True` only when an index expression is a compile-time constant
    within the signed 16-bit range (-32768..32767).
  - When true and the target supports scaled indexing (68020 only),
    `lower_indexed_address()` emits a `.w`-sized index register (e.g.
    `4(a0,d1.w*8)`) instead of the previous always-`.l` operand (e.g.
    `4(a0,d1.l*8)`), producing a smaller/faster operand on 68020.
  - Applied at four call sites in `hasc/codegen_indexed_address.py`: struct-array
    member read and store, array store, and typed-pointer store, wherever a raw
    constant index reaches the indexed-address lowering helper. Typed-pointer
    reads and address-of paths are intentionally excluded (scope decision;
    those paths already constant-fold differently).
  - `--cpu 68000` output is completely unaffected: the `.w` gate requires
    `TargetSpec.supports_scaled_index`, which is only set for 68020.

- **Struct field displacement folding for arbitrary strides on `--cpu 68020`**:
  - `emit_struct_array_read()` and `emit_struct_array_store()` in
    `hasc/codegen_indexed_address.py` now fold a struct field's
    `field_offset` directly into the indexed-addressing operand's
    displacement (e.g. `8(a0,d1.l)`) instead of emitting a separate
    `add.l #8,d1`-style instruction, for struct sizes outside the `{2, 4, 8}`
    scaled-addressing set. This closes part of the gap noted in Phase 1
    above, where struct-array addressing only benefited structs of exactly
    2, 4, or 8 bytes: real-world structs such as the 10-, 11-, and 29-byte
    `explosions`, `Enemy`, and `bullet` structs in
    `examples/games/launchers/launchers.has` now save one instruction per
    struct-field access on 68020.
  - Gated on `codegen.target.supports_scaled_index` (68020 only) and either
    the field offset fitting the signed 8-bit brief-displacement range
    (-128..127) or `target.supports_full_index_extension` for larger
    offsets. `--cpu 68000` output is completely unaffected and continues to
    use the explicit `add.l`-style instruction.
  - Hardened the displacement-range validation in `lower_indexed_address()`
    (`hasc/indexed_address.py`) to apply the brief-range check to any
    non-zero displacement, not only scaled ones, whenever the target lacks
    full-extension support. This is a correctness guard and does not change
    behavior for existing callers.

- **Native 32-bit `muls.l`/`divsl.l` for `*`, `/`, `%` on `--cpu 68020`** (Phase 4
  of `docs/CPU_68020_IMPLEMENTATION_PLAN.md`):
  - `TargetSpec.supports_32bit_muldiv` (`hasc/target.py`) is `True` only for
    `--cpu 68020`. When set, `*`/`/`/`%` on `int`/`long` operands in
    `hasc/codegen.py` now emit a single `muls.l` (multiply) or `divsl.l`
    (divide/modulo, with the remainder captured directly from the paired
    64-bit result register pair) instead of the 68000-only 16-bit-operand
    sequences (`ext.l`+`ext.l`+`muls.w` for multiply; `ext.l`+`divs.w`+`ext.l`
    for divide; `ext.l`+`divs.w`+`swap`+`ext.l` for modulo).
  - **Behavior change on `--cpu 68020` only**: HAS has always required
    multiply/divide/modulo constant operands to fit the signed 16-bit range
    (`-32768..32767`) because the underlying 68000 instructions are
    16-bit-operand only; this restriction is unchanged on `--cpu 68000` (the
    default). Under `--cpu 68020`, this compile-time restriction is now
    **lifted** for `*`, `/`, `%`: full 32-bit constant and runtime operands
    are supported natively, matching what users would expect from a 32-bit
    `int`/`long` type. This is a genuine capability upgrade for 68020 users,
    not just a speed optimization.
  - Division/modulo by a constant `0` remains a compile-time error on both
    targets. See `tests/test_codegen_68020_arithmetic.py`.

- **Native `extb.l` for signed byte-to-long sign extension on `--cpu 68020`**
  (Phase 4 of `docs/CPU_68020_IMPLEMENTATION_PLAN.md`):
  - `TargetSpec.supports_extb_l` (`hasc/target.py`) is `True` only for
    `--cpu 68020`. When set, the two codegen call sites in `hasc/codegen.py`
    that sign-extend a signed `byte` local variable load and a signed
    `byte` stack-parameter load now emit a single `extb.l` instead of the
    68000 two-instruction `ext.w`+`ext.l` sequence.
  - This is a pure optimization: unlike the `muls.l`/`divsl.l` change above,
    there is no compile-time-restriction difference between targets. The
    same signed-byte-arithmetic source compiles successfully under both
    `--cpu 68000` and `--cpu 68020`; only the emitted instruction count
    differs. See `examples/cpu68020_extb_sign_extend.has`.

- **Bare-metal millisecond delay via CIA-A hardware timer**:
  - Added `lib/timer.s` with `WaitMs(ms: int) -> void`, a busy-wait driven by
    CIA-A Timer A one-shot loads on the PAL E-clock (709379 Hz), chained in
    `<=90ms` chunks to work around the CIA's 16-bit timer width.
  - Uses CIA-A only (never CIA-B, which `lib/ptplayer.s` owns for music), so
    `WaitMs` can be used safely alongside music playback.
  - Added `examples/wait_ms_demo.has`, and `scripts/build_example.sh` now
    auto-detects and links `lib/timer.s` when `WaitMs` is used.

- **Exec `AttnFlags` CPU detection support**:
  - Added `lib/cpu.s` with `GetCPUType()`, returning the highest recognized
    68000-through-68060 CPU type reported by Exec.
  - Added HAS constants and the external declaration in
    `examples/includes/cpu_defs.has`, plus the focused
    `examples/cpu_detection.has` usage example.


- **Dependent constant expressions**:
  - `const` initializers may reference constants declared earlier, such as `const B = A + 1;`.
  - Numeric arithmetic, unary signs, parentheses, and existing Q16 conversion remain supported.

- **Mouse button edge API** in `lib/input.s`:
  - Added `GetMouseLBtnPressed`, `GetMouseLBtnReleased`, `GetMouseRBtnPressed`, and `GetMouseRBtnReleased`.
  - Each accessor reports a transition from the latest `ReadMouse` poll and remains valid until the next poll.
- **BOB frame-sequence animation runtime** in `lib/bob_animation.s`:
  - Added create, append, play-once, loop, stop, tick, and destroy operations.
  - `AnimateBob` returns the current BOB handle for direct use with `PasteBob`.
  - Build scripts automatically include the animation, BOB, and heap libraries from `extern` usage.
- **TexturePacker repeated-frame deduplication**:
  - Added opt-in `--deduplicate-frames` to store identical quantized BOB data once.
  - Repeated frames retain descriptor, data, mask, and palette labels as aliases.
  - Default importer behavior remains one complete output file per XML frame.
- **TexturePacker shared descriptor palettes**:
  - Added `--shared-palette`, used with `--shared-palette-file`, to make all atlas BOB descriptors reference one palette block.
  - Avoids duplicate palette words per frame while retaining the existing `CreateBob` descriptor ABI.

## [0.9.0] - 2026-08-11

### Added

- **Conditional compilation directives** `#ifdef`, `#ifndef`, `#else`, `#endif`:
  - Added compile-time branch gating based on `const` declarations.
  - `#ifdef NAME` is true only when `const NAME` is defined and equals `1`.
  - `#ifndef NAME` is true when `NAME` is not defined.
  - Supports nested conditional blocks with optional `#else` branches.

- **DOS-free custom track loader stack** for takeover-mode games:
  - Added runtime library `lib/trackio.s` with direct floppy hardware reads and MFM decode path (no `dos.library` calls):
    - `TrackIoInit`, `TrackIoDone`, `TrackIoGetLastError`, `TrackIoGetFileSize`, `TrackIoReadSector`, `TrackIoReadFile`.
    - Added pre-read size query API so game code can validate destination buffers before `TrackIoReadFile`.
  - Added HAS declarations/constants include: `examples/includes/trackio_defs.has`.
  - Added focused usage example: `examples/trackio_demo.has`.
  - Added ADF container builder: `tools/create_trackio_adf.py` for generating custom data disks compatible with `TrackIoReadFile`.
  - Added dedicated documentation: `docs/TRACKIO_LIBRARY.md` and linked it from `docs/LIBRARY_REFERENCE.md`.

- **Musashi runtime user guide** for Linux-only virtual CPU execution testing:
  - Added `docs/MUSASHI_USER_GUIDE.md` with quickstart, prerequisites,
    expected outputs, troubleshooting, and MMIO PASS/FAIL runtime test authoring.
  - Updated Musashi documentation discoverability links in `README.md` and
    `docs/MUSASHI_RUNTIME_TESTING.md`.

- **Debug logging library documentation** `docs/DEBUG_LIBRARY.md`:
  - Full API reference for `lib/debug.s`: `DebugSetEnabled`, `DebugClear`, `DebugLogStr`, `DebugLogStrRaw`, `DebugLogHex`, `DebugLogInt`, `DebugFlushToDos`.
  - Explains the buffered design and why OS calls cannot be made during OS takeover.
  - Documents buffer limits, overflow policy, and release-build zero-cost pattern.
  - Added `debug.s` row to `docs/LIBRARY_REFERENCE.md`.

### Fixed

- **Codegen register-clobber fix for complex indexed array stores**:
  - Fixed expression normalization so nested parser `Tree` nodes inside `ast.BinOp` are recursively converted before code generation.
  - This prevents losing the left index operand in patterns like `buf[pos + (3 - digit_idx)] = value`, which could previously emit incorrect address computation.
  - Added regression coverage:
    - `tests/test_codegen_basic.py` (`test_complex_index_store_preserves_left_index_operand`)
    - `examples/tests/compiler/index_expr_store_regression.has`

- **Loop `continue` control-flow hardening in optimized assembly**:
  - Prevented a peephole branch-inversion rewrite from collapsing explicit loop-continue jumps in patterns like `if (guard) { continue; }`.
  - This keeps a direct unconditional branch on continue paths to the loop continuation/check label, avoiding rare fallthrough-style regressions in frame-critical update loops.
  - Added dedicated regression tests in `tests/test_codegen_continue_regression.py` covering:
    - single-level `for` continue guard
    - nested `if/else` with continue
    - continue before inline `asm`
    - continue with subsequent array writes
    - continue behavior in `while`, `do-while`, and `repeat` loops

- **Parser optional-slot normalization for declarations and macros**:
  - Fixed transformer handling of Lark optional placeholders so omitted optional grammar parts no longer leak `None` into AST construction.
  - This resolves parse/codegen failures seen in array declarations without explicit size suffixes and in included macro bodies.
  - Affected examples now compile cleanly again:
    - `examples/tests/compiler/array_access_test.has`
    - `examples/tests/compiler/array_comprehensive_test.has`
    - `examples/tests/compiler/arrays_test.has`
    - `examples/tests/compiler/include_test.has`

## [0.8] - 2026-07-31

### Added

- **AmigaDOS file I/O library** in `lib/fileio.s` with HAS interop-friendly wrappers:
  - Added `FileIoInit`, `FileIoDone`, `FileIoErr`, `FileOpen`, `FileClose`, `FileRead`, `FileWrite`, `FileSeek`, `FileDelete`, `FileRename`, `FileLock`, `FileUnLock`, and `FileExamine`.
  - Added HAS declaration/constants include: `examples/includes/fileio_defs.has`.
  - Added takeover-safe usage example: `examples/fileio_demo.has`.
  - Added compiler regression example for missing-file `IoErr` flow: `examples/tests/compiler/fileio_missing_file_ioerr_test.has`.
  - Corrected seek constants to canonical DOS values (`OFFSET_BEGINNING=-1`, `OFFSET_CURRENT=0`, `OFFSET_END=1`).
  - Added helper build script: `scripts/build_fileio_demo.sh`.
  - Added loading-UI hook pattern in `examples/fileio_demo.has` (example-level, not library-level) and documented the flow in `docs/FILE_IO_LIBRARY.md`.
  - Added dedicated API guide: `docs/FILE_IO_LIBRARY.md` and linked it from `docs/LIBRARY_REFERENCE.md`.
  - Intended runtime pattern is explicit: `ReleaseSystem()` before DOS I/O, `TakeSystem()` after DOS I/O.

- **Linux-only Musashi runtime-test scaffolding** for selected execution tests:
  - Added pinned Musashi lock file: `tools/musashi.lock`.
  - Added Linux scripts:
    - `scripts/setup_musashi.sh` (clone + checkout pinned Musashi ref)
    - `scripts/build_musashi_runner.sh` (build local host runner)
    - `scripts/test_runtime_musashi.sh` (compile/assemble/execute selected runtime tests)
    - `scripts/update_musashi_pin.sh` (refresh lock to an exact new commit)
  - Added host runner source: `tools/musashi_runner/has_musashi_runner.c`.
  - Added selected runtime smoke examples and manifest:
    - `examples/runtime_musashi/smoke_mmio_pass.has`
    - `examples/runtime_musashi/proc_math_branch_pass.has`
    - `tests/runtime_musashi_manifest.txt`
  - Added optional pytest wrapper: `tests/test_runtime_musashi.py`.
  - Added documentation: `docs/MUSASHI_RUNTIME_TESTING.md`.
  - This tier is explicitly Linux-only for now and intended for on-demand runtime
    emulation checks, while existing parser/codegen/link tests remain unchanged.

- **VBCC interop test wrappers**:
  - Added `scripts/tests/test_vbcc_interop.sh` and `scripts/tests/test_vbcc_interop.ps1` as direct entrypoints for the vbcc interop test suite.
  - This provides a consistent cross-platform command surface for contributor and CI-style interop checks.

- **Branchless Scc boolean assignment** and **DBcc counter-loop** codegen fast paths
  (see `docs/CODEGEN_SCC_DBCC_TIPS.md`):
  - `if <comparison> { v = 1 } else { v = 0 }` (and the 0/1-swapped form) now compiles
    to a branchless `cmp`+`Scc`+`andi`+`neg` sequence instead of a branchy if/else with
    labels. Applies to `==`, `!=`, `<`, `<=`, `>`, `>=`, including unsigned comparisons;
    falls back to the normal branchy path for any other pattern (different assignment
    targets per branch, non-0/1 literals, multi-statement branches, etc.).
  - `for i = start to end [by step] { body }` compiles to a single `dbra` instruction
    when `start`/`end`/`step` are compile-time constants and the loop variable `i` is
    never read or written in the body (including via macro expansion or an inline-asm
    `@i` substitution) - eliminating the per-iteration load/compare/increment/store
    entirely. Loops nested inside another active `dbra`-based loop (`for` or `repeat`)
    automatically save/restore the shared `d7` counter register around the inner loop.
  - New example `examples/tests/compiler/scc_dbcc_optimization_test.has` demonstrates both fast paths
    and their general-path fallback cases.
  - New tests in `tests/test_scc_dbcc_codegen.py` cover both optimizations end-to-end
    and unit-test the loop-variable-usage analysis directly.

- **BOB mirror APIs** in `lib/bob.s`:
  - Added `MirrorBobHorizontally(handle) -> int`.
  - Added `MirrorBobVertically(handle) -> int`.
  - Both APIs create a new BOB handle with mirrored data+mask, preserve the source palette pointer, preserve save-background policy (including background allocation when enabled), return the new handle on success, and `-1` on failure.

- **Dead-procedure elimination pass** (`--strip-unused-procs` / `--strip-unused-report`):
  - New module `hasc/reachability.py` performs conservative call-graph analysis after validation and before code generation.
  - Roots are discovered from `public` declarations that point to internal `proc` definitions.
  - Unreachable internal procedures are removed from the AST before assembly is emitted.
  - Three conservative keep-all safeguards prevent incorrect stripping:
    - **Feature off by default** â€” requires an explicit opt-in flag.
    - **Top-level asm block** â€” raw `jsr`/`jmp` may reference any label; all procs kept.
    - **No roots found** â€” keeps everything rather than silently discarding all code.
  - `--strip-unused-report` prints roots, kept, and removed procedure lists to stderr.
  - Three new example files demonstrate all scenarios: `strip_unused_procs_demo.has`, `strip_unused_procs_asm_safe.has`, `strip_unused_procs_no_roots.has`.

- **Example suite split gate** for deterministic regression checks:
  - Added `examples/tests/compiler/negative_examples.txt` manifest for expected-fail examples.
  - Added `scripts/tests/test_examples_split.sh` to enforce:
    - positive examples must compile
    - negative examples must fail
    - non-zero exit code on any mismatch (CI-friendly)
- **GUI ComboBox widget** (`lib/gui.s` / `lib/gui.i`):
  - Added `DrawComboBox(gadget_ptr)` — renders a selectable list from a semicolon-separated, NUL-terminated item string.
  - Normal and selected rows use independent background/text palette pairs (`COMBOBOX_BG`/`COMBOBOX_TCOLOR` vs `COMBOBOX_SELBG`/`COMBOBOX_SELTEXT`).
  - Added `GADGET_TYPE_COMBOBOX = 3`; `DrawGadget` now dispatches combo boxes transparently.
  - Added `COMBOBOX` struct (26 bytes, `gui.i`): offsets `0..19` are layout-compatible with `GADGET`.
  - Added end-to-end example `examples/combobox_demo.has`.

- **`DrawMsgBoxCaption` function** (`lib/gui.s` / `lib/gui.i`):
  - Added `DrawMsgBoxCaption(x, y, w, h, bg, border, caption, str, tc)` — bordered window with an optional title caption rendered in the top border row.
  - Caption is clipped to the available text width (`w/8 - 2` chars) automatically.
  - `DrawMsgBox` is now a thin wrapper calling `DrawMsgBoxCaption` with `caption = 0`; existing code is unaffected.
  - Added end-to-end example `examples/msgbox_caption_demo.has`.

- **GUI library documentation** updated in `docs/GUI_LIBRARY.md`:
  - Added `DrawMsgBoxCaption` and `DrawComboBox` API references.
  - Added `COMBOBOX` struct field table.
  - Updated `DrawGadget` dispatch table and `extern func` declaration snippet.


  - Added `DrawEditBox(x,y,w,h,bg,border,text_ptr,tc,cursor_pos,cursor_vis)` single-line editable text field renderer.
  - Added `EditBoxProcessKey(text_ptr,max_len,cursor_pos_ptr,scancode)` for scan-code-driven insert/delete/cursor movement.
  - Added `EditBoxPollKey(text_ptr,max_len,cursor_pos_ptr)` convenience wrapper consuming `keyboard.s` `current_key`.
  - Added `GADGET_TYPE_EDITBOX=2` and `EDITBOX_*` struct layout (28 bytes, `0..19` layout-compatible with `GADGET`).
  - `DrawGadget(gadget_ptr)` now dispatches edit boxes (type 2), including focused border and cursor visibility via `EDITBOX_FLAGS`.
  - Added end-to-end example `examples/editbox_demo.has`.

### Changed

- Documentation clarification: README and compiler developer guidance now explicitly define HAS as C-like surface syntax with assembly-first semantics and maintainer guardrails against feature drift. This is documentation-only; compiler behavior is unchanged.
- Changelog note style guidance: future entries that affect emitted code should include a short "Assembly impact" note (for example: "Assembly impact: no emitted-instruction change" or "Assembly impact: fewer branches in boolean lowering") so codegen cost implications are easy to scan.

- **Longword alignment for every emitted section**:
  - Code generation now emits `cnop 0,4` immediately after every `SECTION` directive
    (`data`/`data_c`, `bss`/`bss_c`, `code`/`code_c`), guaranteeing the first label in
    each section starts on a 4-byte boundary regardless of linking order.
  - This is in addition to the existing per-variable `even` alignment already emitted
    for word/long data and bss variables.
  - Extended the same convention to the standalone asset-generator tools
    (`tools/bob_importer.py`, `tools/c64_font_converter.py`, `tools/frame_merger.py`,
    `tools/iff_importer.py`, `tools/sprite_importer.py`,
    `tools/texturepacker_atlas_importer.py`, `tools/tile_importer.py`): every
    `SECTION` directive they emit is now immediately followed by `CNOP 0,4`.
  - Fixed `tools/frame_merger.py` to strip the redundant per-file `CNOP` line from
    each input frame file when consolidating multiple frame files under one merged
    `SECTION` (it already stripped the per-file `SECTION`/`XDEF` lines the same way).

- **Parameter increment/decrement codegen semantics**:
  - Pre/post `++` and `--` on procedure parameters now preserve parameter storage semantics for both stack and `__reg(...)`-annotated extern-style register parameters.
  - This aligns generated code with expected mutation behavior when parameter-backed lvalues are used in update expressions.

- **Statement-form increment/decrement codegen tightening**:
  - Standalone `++`/`--` statements now emit direct storage/register updates without loading an unused temporary result register.
  - Expression semantics are unchanged: post-increment/post-decrement in value contexts still preserve old-value behavior.

- **Documentation drift cleanup** across README and docs:
  - Updated README project structure to match current `hasc/` and `tools/` layout.
  - Replaced stale/missing documentation links with existing targets.
  - Corrected outdated example references and sprite-tool cross-links.
  - Aligned contributor/developer docs with current version and example-driven testing workflow.

- **BOB lifecycle update** in `lib/bob.s`:
  - `DestroyBob(handle)` now frees mirrored owned data/mask buffers for handles created by mirror APIs, in addition to freeing background buffer (if present) and runtime struct.

- `extern func` call emission now honors `__reg(...)` parameter annotations during code generation.
  - Register-annotated extern args are loaded into declared registers before `jsr`.
  - Non-annotated extern args continue to use right-to-left stack passing.
  - Stack cleanup now reflects only stack-passed extern args for mixed signatures.
- Updated example startup style in `examples/execution_order_demo.has` and `examples/tests/compiler/push_pop_test.has` to use explicit startup `asm` bootstrap (`jsr ...` + `rts`) instead of top-level `call` statements.
- Updated `examples/return_values.has` manual return-register demonstration to valid explicit assembly (`move.l d0,result`) instead of pseudo-variable usage.
- Updated `examples/tests/compiler/heap_test.has` to valid HAS section syntax for heap buffer declaration (`bss` + array declaration) and parser-compatible comment style.
- Added extern ABI behavior examples:
  - `examples/extern_reg_params.has` (all-register extern params)
  - `examples/extern_mixed_params.has` (mixed register + stack extern params)
  - `examples/extern_stack_only.has` (stack-only extern params)
- GUI keyboard split for EditBox polling:
  - Moved `EditBoxPollKey` implementation from `lib/gui.s` to new `lib/gui_keyboard.s`.
  - Updated build integration/dependency closure to include `gui_keyboard.s` when GUI/editbox symbols are used.

### Fixed

- Resolved all previously identified stale positive-example failures in split-gate checks:
  - `examples/execution_order_demo.has`
  - `examples/tests/compiler/push_pop_test.has`
  - `examples/tests/compiler/heap_test.has`
  - `examples/return_values.has`
- Example split gate now passes with:
  - Positive suite: 79/79
  - Negative suite: 5/5 expected failures
- Added validator diagnostics for invalid extern register signatures:
  - duplicate register assignments in a single `extern func` signature
  - reserved register usage (`a6`, `a7`) in `extern func` params
- **68000 even-address alignment in the BSS section emitter**: a byte-sized reservation
  (`ds.b`) immediately followed by a word/long reservation could previously place the
  word/long variable on an odd address, which triggers a 68000 address error at runtime.
  The BSS emitter now tracks the running byte offset per section and inserts an `even`
  directive only when a word/long variable (or a struct containing any word/long field)
  would otherwise start at an odd address.
- **Removed redundant `even` directives in the DATA section emitter**: it previously
  emitted `even` unconditionally before every single variable regardless of whether it
  was needed. It now uses the same offset-tracking logic as the BSS fix above, so
  byte-only data and already-aligned word/long data no longer get a pointless `even`.
  Generated assembly is unaffected in correctness, only smaller/cleaner. No HAS syntax
  changes.

#### GUI Widget Library (`lib/gui.s` / `lib/gui.i`)
- **`DrawButton(x, y, w, h, bg, border, label, tc)`**: Clickable button gadget with centred label.
  - Renders a **3D raised effect**: flat `bg` fill, `border`-coloured highlight on top and left edges, colour-0 (black) shadow on bottom and right edges.
  - Horizontal centering: `cx = (x + (w âˆ’ label_px) / 2) / 8` (pixel-exact, snapped to char grid).
  - Vertical centering: `cy = (y + h/2) / 8` (rounds to nearest char row; use `h â‰¥ 24` for perfect 7 px inner gap).
- **`GuiPollMouse()`**: Per-frame mouse event accumulator.
  - Reads `GetMouseDX/DY` and accumulates into internal `gui_abs_mouse_x/y` (clamped to screen bounds; mode-aware).
  - Leading-edge detection on left button â†’ `gui_lbtn_edge` flag.
  - Must be called once per frame after `ReadMouse()`.
- **`GuiHitTestRect(x, y, w, h)`**: Returns 1 if the left button was just pressed inside the given pixel rect. Suitable for inline buttons in HAS without a GADGET struct.
- **`GuiHitTest(gadget_ptr)`**: Same click detection driven by a GADGET struct.
- **`GetGuiMouseX()` / `GetGuiMouseY()`**: Zero-frame accessors returning the current accumulated absolute mouse pixel position as a signed long. Use these to feed a hardware sprite cursor.
  - **`DrawGadget(gadget_ptr)`**: Struct-based widget dispatcher. Type 0 â†’ `DrawMsgBox`, type 1 â†’ `DrawButton`.
- **GADGET struct** (20 bytes, defined in `lib/gui.i`): `X, Y, W, H, BG, BORDER, TEXT (long), TCOLOR, TYPE`.
- **Hardware sprite mouse cursor** in `examples/msgbox_demo.has`:
  - 11-line classic arrow shape defined in a `data cursor_data:` section (fast RAM; `CreateSprite` copies to chip RAM).
  - Palette: color1 = white (`$FFF`), color2 = light-grey (`$CCC`), color3 = mid-grey (`$888`).
  - Initialised with `CreateSprite(0, &cursor)` + `ApplySpritePalette(0)` + `ShowSprite(0)`.
  - Updated every VBlank: `SetSpritePosition(0, GetGuiMouseX(), GetGuiMouseY())`.
- **`scripts/build_msgbox_demo.sh`**: End-to-end build script compiling, assembling, and linking all eight objects for the GUI demo.
- **New documentation**: [`docs/GUI_LIBRARY.md`](GUI_LIBRARY.md) â€” full API reference for the GUI widget library.

### Changed
- **`DrawButton` rendering** changed from a uniform `DrawBox` border to a **3D raised gadget** style (bright top/left highlight, black bottom/right shadow). Visual appearance now clearly distinguishes buttons from message-box windows.
- **`DrawButton` vertical centering** formula changed from `(y/8) + (h/8âˆ’1)/2` to `(y + h/2) / 8`, which rounds to the nearest character row rather than the topmost. For `h = 16`, text is now placed in the lower half of the button face instead of starting at the top border pixel.
- **`examples/msgbox_demo.has`** button dimensions updated from `(120, 240, 80, 16)` to `(100, 232, 120, 24)` to achieve perfect 7 px inner gap centering and give the button a standard Amiga gadget proportion. Window 4 height reduced from 48 to 40 px to accommodate the taller button within the 256-line screen.
- **`lib/gui.i`** updated with `XREF` declarations and HAS `extern func` comment templates for `DrawButton`, `GuiPollMouse`, `GuiHitTest`, `GuiHitTestRect`, `GetGuiMouseX`, and `GetGuiMouseY`.

### Added
- **`#pragma strict16arith(on|off)`**: New compile-time control for 68000 word arithmetic safety checks.
  - `off` (default): preserves permissive behavior for dynamic arithmetic.
  - `on`: requires arithmetic operands used by `muls.w` / `divs.w` paths to be provably safe signed 16-bit values.

### Changed
- Optimized comparison branch emission now selects unsigned branch opcodes (`blo`, `bls`, `bhi`, `bcc`) when operand types are unsigned.
- Stack-based signed narrow parameters (`byte`, `word`) are now sign-extended correctly during loads.

### Fixed
- Removed incorrect signed division-by-power-of-two rewrite to `asr`, preserving `divs.w` semantics for negative values.
- Fixed duplicate RHS evaluation in non-constant division code paths.
- Added codegen diagnostics for constant `*`, `/`, `%` operands outside signed 16-bit range where 68000 word arithmetic is required.
- Added diagnostics for constant divide/modulo by zero.

## [0.4] - 2026-02-05

### New Features

#### Language Enhancements
- **Automatic Q16.16 Floating-Point Conversion**: Natural decimal syntax
  - Write floating-point literals directly: `2.5`, `0.98`, `43.55`
  - Compiler automatically converts to Q16.16 fixed-point format at compile-time
  - Formula: `Q16.16 = int(float_value × 65536)`
  - Works in constants, data sections, and inline literals
  - Zero runtime overhead - all conversion happens during compilation
  - See [docs/Q16_AUTOMATIC_CONVERSION.md](Q16_AUTOMATIC_CONVERSION.md) for details
  - Examples: [q16_float_test.has](../examples/tests/compiler/q16_float_test.has), [q16_comprehensive_test.has](../examples/tests/compiler/q16_comprehensive_test.has)

### Documentation
- Added comprehensive Q16 automatic conversion documentation
- Updated README with Q16.16 fixed-point feature
- Added example files demonstrating float to Q16 conversion

### Fixed
- Documented that `extern func` calls are currently emitted with stack-based argument passing even when `__reg(...)` annotations are present, matching the existing hand-written routines in `lib/`

## [0.3] - 2026-01-29

### New Features

#### Language Enhancements
- **Native Keyword**: Zero-overhead assembly functions with `native` keyword
  - Eliminates stack frame setup/teardown (`link`/`unlk` instructions)
  - Requires all parameters to be register-based (`__reg`)
  - No local variable allocation allowed
  - Ideal for performance-critical assembly-only functions
  - See [docs/NATIVE_KEYWORD.md](NATIVE_KEYWORD.md) for details

- **Struct Pointer Arrow Operator**: C-style arrow syntax for cleaner code
  - `p->field` as syntactic sugar for `(*p).field`
  - Significantly improves code readability
  - Same performance as explicit dereference
  - Both syntaxes supported and produce identical assembly
  - See [docs/STRUCT_POINTERS.md](STRUCT_POINTERS.md) for details

#### Tools
- **Tile Graphics Importer**: New `tile_importer.py` tool for converting tile-based graphics

#### Documentation
- Comprehensive documentation for native keyword feature
- Updated struct pointer documentation with arrow operator examples
- Removed deprecated DBRA loop syntax documentation
- Added native keyword to VS Code extension syntax highlighting
- Updated README with new features

### Improvements
- VS Code extension now recognizes `native` keyword
- "Go to Definition" and hover support for native functions
- Better organization of asset conversion tools in documentation

## [0.2] - 2025-12-31

### Major Features

#### Core Language
- Complete Motorola 68000 code generation pipeline
- Strong type system with automatic type promotion
- Procedures with forward declarations (`func` keyword)
- External function imports (`extern func` keyword)
- Multiple memory sections (code, data, bss) with proper alignment
- Constants with compile-time evaluation
- Structs with field access
- Comprehensive operator support:
  - Arithmetic: +, -, *, /, %
  - Bitwise: &, |, ^, ~
  - Shift: <<, >>
  - Logical: &&, ||, !
  - Comparison: ==, !=, <, >, <=, >=
  - Pointer: &, *
  - Assignment: =, +=, -=, *=, /=, etc.
  - Increment/Decrement: ++, --

#### Advanced Features
- External Python code generation via `--generate` flag
- Macro system with parameter substitution
- Inline Python execution with `@python` directive
- Include system with cyclic dependency detection
- Inline assembly support with `asm { }` blocks
- Register manipulation with `getreg()` and `setreg()` intrinsics

#### Arrays and Pointers
- Single and multi-dimensional array support
- Array initialization with literal values
- Pointer arithmetic and dereferencing
- Address-of operator (`&`)
- Dynamic array access with computed indices

#### Control Flow
- if/else statements
- for loops (C-style)
- while loops
- do-while loops
- break and continue statements
- 68000-specific `dbra` loop optimization

#### Register Allocation
- Smart register allocator with data (d0-d7) and address (a0-a6) registers
- Calling convention compliance (caller-save/callee-save)
- Spill-to-stack when registers exhausted
- Frame pointer management with `link`/`unlk` instructions
- Register parameter passing via `__reg()` annotation

#### Amiga-Specific Features
- Hardware register access (CUSTOM, CIA, etc.)
- Graphics library interface (copper lists, sprites, blitter)
- HAM6 (Hold-And-Modify) graphics mode support
- Heap management primitives
- System library integration (Exec, Graphics, etc.)

#### Validation and Error Handling
- Two-pass semantic validation
- Symbol resolution (constants, variables, functions)
- Type checking with promotion rules
- Array bounds validation
- Circular dependency detection
- Informative error messages with line numbers
- `#warning` and `#error` preprocessor directives

#### Code Generation
- Optimized instruction selection for 68000
- Efficient address mode usage
- Expression evaluation with register reuse
- Stack frame optimization
- PC-relative addressing where appropriate
- Proper instruction sizing (.b, .w, .l suffixes)

### Tools and Scripts
- `build.sh` - Automated vasm/vlink build script
- `create_disk.sh` - Amiga ADF disk creation utility

### Documentation
- Comprehensive README with quick start guide
- Language feature tutorials and examples
- Compiler architecture documentation
- Implementation details for all subsystems
- Step-by-step Python integration guide

### Examples
- 60+ example programs covering all features
- Basic examples (variables, types, operators)
- Control flow demonstrations
- Array and pointer usage
- Advanced features (macros, Python)
- Amiga-specific examples (graphics, hardware)
- Code generation examples

### Known Issues
- No floating-point support (68000 has no FPU)
- Limited struct support (no nested structs)
- No cross-procedure optimization

### Technical Details
- Parser: Lark-based EBNF grammar
- AST: Dataclass-based strongly-typed tree
- Validator: Two-pass symbol resolution
- Code Generator: ~2500 lines with full 68000 instruction support
- Target: Motorola 68000 (Amiga 500/1000/2000)
- Output: vasm-compatible assembly

---

## [0.1] - 2025-12-01 (Initial Prototype)

### Initial Features
- Basic parser with Lark
- Simple procedure definitions
- Variable declarations
- Data and code sections
- Inline assembly support
- Basic code generation

---

## Future Plans

### Planned for 0.3
- Floating-point library integration
- Enhanced optimization passes
- Improved error messages with suggestions
- Nested struct support
- Cross-procedure inlining
- Dead code elimination

### Long-term Goals
- Debugger integration
- IDE language server support
- Standard library expansion
- Profile-guided optimization
- Additional target platforms (68030 and later)
- Built-in unit testing framework

---

**Note**: This project is in constant development. Features and APIs may change between versions.
