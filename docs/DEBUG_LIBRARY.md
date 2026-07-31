# HAS Debug Logging Library (`lib/debug.s`)

A lightweight, buffered debug logger for Amiga takeover-style programs.  
All messages are collected in a RAM buffer while the game owns the hardware,  
then flushed to the CLI shell in a single safe `dos.library` write after `ReleaseSystem()`.

---

## Contents

1. [Why a buffered logger?](#why-a-buffered-logger)
2. [Design overview](#design-overview)
3. [Including the library](#including-the-library)
4. [API reference](#api-reference)
   - [DebugSetEnabled](#debugsetenabled)
   - [DebugClear](#debugclear)
   - [DebugLogStr](#debuglogstr)
   - [DebugLogStrRaw](#debuglogstrraw)
   - [DebugLogHex](#debugloghex)
   - [DebugLogInt](#debuglogint)
   - [DebugFlushToDos](#debugflushtodos)
5. [Usage pattern](#usage-pattern)
6. [Release builds](#release-builds)
7. [Buffer limits](#buffer-limits)
8. [Build integration](#build-integration)

---

## Why a buffered logger?

Amiga takeover programs call `TakeSystem()` to disable OS multitasking and gain
exclusive hardware access.  Inside that window **all `dos.library` calls are
forbidden** — the OS task switcher is off and calling AmigaDOS would deadlock or
corrupt system state.

`lib/debug.s` solves this by collecting every log message into a plain 4 KB RAM
buffer.  After `ReleaseSystem()` restores the OS, a single call to
`DebugFlushToDos()` dumps everything to the current CLI output.  The full message
history is available despite the OS blackout window.

---

## Design overview

```
DebugLogStr / DebugLogHex / DebugLogInt
         │
         ▼  (if enabled)
  ┌──────────────────┐
  │  debug_buffer    │  4096-byte RAM region (DATA section)
  │  (4 KB, clipped) │  write cursor = debug_used (word)
  └──────────────────┘
         │
         ▼  (after ReleaseSystem)
  DebugFlushToDos
  ├── opens dos.library
  ├── Write(Output(), debug_buffer, debug_used)
  └── closes dos.library, resets debug_used
```

Key design decisions:

- **Zero overhead when disabled** — every log function tests `debug_enabled` first
  and returns immediately on zero, so disabling logging costs one `tst.w` + branch.
- **Buffer overflow is silently clipped**, not wrapped — the latest messages are
  preserved and the oldest are never overwritten.
- **INT_MIN handled explicitly** — `DebugLogInt` does not attempt `neg.l
  $80000000` (which would overflow), and instead emits the string literal
  `"-2147483648"` directly.
- **No OS calls during logging** — all append functions manipulate the buffer
  directly in RAM.  Only `DebugFlushToDos` opens `dos.library`.

---

## Including the library

**HAS** — declare each function you call inside your `code` block:

```has
extern func DebugSetEnabled(flag: int) -> int;
extern func DebugClear() -> int;
extern func DebugLogStr(msg: int) -> int;
extern func DebugLogHex(value: int) -> int;
extern func DebugLogInt(value: int) -> int;
extern func DebugFlushToDos() -> int;
```

**Build command** — link `debug.s` together with your other objects:

```sh
vasmm68k_mot -Fhunkexe -I lib/ -o build/my_game.o build/my_game.s \
  lib/takeover.s lib/debug.s
vlink -bamigahunk build/my_game.o -o build/my_game.exe
```

---

## API reference

### `DebugSetEnabled`

```c
DebugSetEnabled(flag: int) -> int
```

Enables or disables the logging module globally.

- `flag != 0` — logging is active; all `DebugLog*` calls append to the buffer.
- `flag == 0` — logging is inactive; all `DebugLog*` calls return immediately.

Does **not** clear the buffer.  Call `DebugClear()` separately if you want to
start with an empty log.

| Argument | Meaning |
|----------|---------|
| `flag` | Non-zero to enable, zero to disable |

Returns `d0 = 0`.

---

### `DebugClear`

```c
DebugClear() -> int
```

Resets the write cursor to zero, effectively discarding all buffered content.

- Does not zero-fill the buffer — only the cursor is reset.
- Does not check `debug_enabled` — always succeeds.
- Safe to call before `DebugSetEnabled`.

Returns `d0 = 0`.

---

### `DebugLogStr`

```c
DebugLogStr(msg_ptr: int) -> int
```

Appends a NUL-terminated string to the buffer, followed by a line feed (`LF = 0x0A`).

- Silently returns when `debug_enabled == 0`.
- Stops appending if the buffer is full (remaining characters are dropped).
- The trailing LF is also dropped on overflow rather than a partial line being written.

| Argument | Meaning |
|----------|---------|
| `msg_ptr` | Pointer to a NUL-terminated message string |

Returns `d0 = 0`.

```has
data msgs:
    msg_start.b = "[DBG] start", 0

// In your proc:
call DebugLogStr(&msg_start);
```

---

### `DebugLogStrRaw`

```c
DebugLogStrRaw(msg_ptr: int) -> int
```

Identical to `DebugLogStr` but **does not append a line feed**.  Use this to
build a compound log line across multiple calls, then terminate with a `"\n"` string.

| Argument | Meaning |
|----------|---------|
| `msg_ptr` | Pointer to a NUL-terminated string fragment |

Returns `d0 = 0`.

---

### `DebugLogHex`

```c
DebugLogHex(value: int) -> int
```

Formats `value` as a fixed-width 8-digit hexadecimal string and appends it with a
trailing line feed.

Output format: `0xXXXXXXXX` (always 10 characters + LF).

- Digits `A`–`F` are uppercase.
- Leading zeros are included; the width is always 8 nibbles.

| Argument | Meaning |
|----------|---------|
| `value` | Any 32-bit value (treated as unsigned for formatting) |

Returns `d0 = 0`.

```has
call DebugLogHex($DEADBEEF);    // appends "0xDEADBEEF\n"
call DebugLogHex(custom_reg);   // hardware register snapshot
```

---

### `DebugLogInt`

```c
DebugLogInt(value: int) -> int
```

Formats `value` as a signed decimal string and appends it with a trailing line feed.

- Handles the full 32-bit signed range, including `INT_MIN` (`-2147483648`).
- Uses a software divide-by-10 loop compatible with all 68000 variants.
- No leading zeros or padding.

| Argument | Meaning |
|----------|---------|
| `value` | Signed 32-bit integer |

Returns `d0 = 0`.

```has
var score: int = 42;
call DebugLogInt(score);        // appends "42\n"
call DebugLogInt(-12345);       // appends "-12345\n"
```

---

### `DebugFlushToDos`

```c
DebugFlushToDos() -> int
```

Writes the entire accumulated buffer to the current CLI output via `dos.library`
and then resets the buffer.

**Call only after `ReleaseSystem()`.**  Calling this while the OS is taken over
will deadlock or crash.

Internally:

1. Opens `dos.library` via `_LVOOldOpenLibrary`.
2. Calls `Output()` to get the current DOS file handle (the CLI window).
3. Calls `Write(handle, debug_buffer, debug_used)`.
4. Closes `dos.library`.
5. Resets `debug_used = 0`.

If `debug_enabled == 0` or the buffer is empty the function returns without
opening `dos.library`.  If `dos.library` cannot be opened the buffer is not reset
(the data is preserved for a retry or manual inspection).

Returns `d0 = 0`.

---

## Usage pattern

This is the canonical usage order for a takeover game:

```has
const DEBUG_LOG = 1;    // set to 0 in release builds

code game:
    extern func TakeSystem() -> void;
    extern func ReleaseSystem() -> void;
    extern func DebugSetEnabled(flag: int) -> int;
    extern func DebugClear() -> int;
    extern func DebugLogStr(msg: int) -> int;
    extern func DebugLogHex(value: int) -> int;
    extern func DebugLogInt(value: int) -> int;
    extern func DebugFlushToDos() -> int;

    public main;

    asm {
        jsr main
        rts
    }

    proc main() -> int {
        // 1. Enable and reset before takeover.
        call DebugSetEnabled(DEBUG_LOG);
        call DebugClear();
        call DebugLogStr(&msg_boot);

        // 2. OS is taken over — buffer-only logging from here.
        call TakeSystem();
        call DebugLogStr(&msg_takeover);
        call DebugLogHex($DEADBEEF);    // register snapshot
        call DebugLogInt(-12345);       // variable value

        // 3. Restore OS before any DOS output.
        call ReleaseSystem();
        call DebugLogStr(&msg_release);

        // 4. Flush everything to CLI in one safe write.
        call DebugFlushToDos();
        return 0;
    }

data log_msgs:
    msg_boot.b     = "[DBG] boot", 0
    msg_takeover.b = "[DBG] takeover active", 0
    msg_release.b  = "[DBG] system released", 0
```

Expected CLI output after the program exits:

```
[DBG] boot
[DBG] takeover active
0xDEADBEEF
-12345
[DBG] system released
```

See the full runnable example: [examples/debug_log_demo.has](../examples/debug_log_demo.has)

---

## Release builds

Setting `DEBUG_LOG = 0` and passing it to `DebugSetEnabled` means every log call
exits after a single `tst.w debug_enabled` / `beq` — two instructions.  The
buffer is allocated at link time and cannot be removed without rebuilding, but at
**4 KB** it is negligible in a typical Amiga program.

If you want zero memory overhead in release builds, conditionally call
`DebugSetEnabled` only when `DEBUG_LOG != 0`:

```has
if (DEBUG_LOG != 0) {
    call DebugSetEnabled(1);
}
```

Since `DEBUG_LOG` is a compile-time constant, the compiler eliminates the branch
entirely and the `DebugSetEnabled` call is never emitted.

---

## Buffer limits

| Parameter | Value |
|-----------|-------|
| Buffer size | 4096 bytes |
| Overflow policy | Clip (no wrap; oldest messages are kept) |
| Max line length | No per-line limit; limited by remaining buffer space |
| Hex line fixed width | 10 characters (`0x` + 8 nibbles) + 1 LF |
| Decimal line max width | 11 characters (`-2147483648`) + 1 LF |

If the buffer fills up during the takeover window, the latest messages are silently
dropped.  Increase `DEBUG_BUFFER_SIZE` in `debug.s` and recompile if you need
more capacity.

---

## Build integration

`debug.s` has no dependencies beyond the standard Amiga includes (`hardware.i`,
`exec_lib.i`).  Link it alongside any other `lib/` objects:

```sh
# Minimal debug build
vasmm68k_mot -Fhunkexe -I lib/ -o build/game.o build/game.s \
  lib/takeover.s lib/debug.s
vlink -bamigahunk build/game.o -o build/game.exe

# With graphics and GUI
vasmm68k_mot -Fhunkexe -I lib/ -o build/game.o build/game.s \
  lib/takeover.s lib/graphics.s lib/gui.s lib/debug.s
vlink -bamigahunk build/game.o -o build/game.exe
```
