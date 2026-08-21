# AmigaDOS CLI Output Library (`lib/dos.s`)

`lib/dos.s` provides thin wrappers for writing text and numbers to the current CLI/Workbench stdout stream via AmigaDOS, so non-bare-metal HAS programs can print output using normal `extern func` calls.

## Safety model with takeover

If your program uses `TakeSystem()` (takeover-based games), do not call DOS APIs while takeover is active. The same rule as `lib/fileio.s` applies:

Safe pattern:

1. `ReleaseSystem()`
2. `InitDOS()` and output calls (`PrintOut`/`PrintOutLen`/`PrintNum`)
3. `CloseDOS()`
4. `TakeSystem()`

`lib/dos.s` is independent of `lib/fileio.s` and `lib/debug.s`: each module caches its own `dos.library` base separately, following the existing repo convention.

See also the runtime example in `examples/dos_hello.has`.

## Include declarations

Use:

```has
#include "includes/dos_defs.has";
```

This include provides `extern func` declarations for all exported symbols.

## API reference

### `InitDOS() -> int`

Opens `dos.library` and caches its base plus the current CLI/Workbench stdout handle (via DOS `Output()`).

- Returns `0` on success.
- Returns `-1` on failure.
- Idempotent: if already initialized, returns success without reopening.

### `CloseDOS() -> int`

Closes the cached `dos.library` base if open, and clears the cached base and stdout handle.

- Returns `0`.
- Idempotent: safe to call even when not initialized.

### `PrintOut(msg: ptr) -> int`

Scans `msg` for its NUL terminator, then writes it via DOS `Write()` to the cached stdout handle.

- `msg`: pointer to a NUL-terminated string.
- Returns bytes written on success.
- Returns `-1` if `InitDOS()` was not called or `Write()` failed.

### `PrintOutLen(msg: ptr, length: int) -> int`

Writes exactly `length` bytes via DOS `Write()` without scanning for a NUL terminator.

- `msg`: pointer to the data to write.
- `length`: number of bytes to write.
- Returns bytes written on success.
- Returns `-1` if `InitDOS()` was not called or `Write()` failed.

### `PrintNum(value: int) -> int`

Formats `value` as a signed 32-bit decimal string (no trailing newline) and writes it via DOS `Write()` to the cached stdout handle.

- `value`: signed 32-bit integer to format.
- Returns bytes written on success.
- Returns `-1` if `InitDOS()` was not called or `Write()` failed.

## Usage pattern

1. `InitDOS()`
2. `PrintOut`/`PrintOutLen`/`PrintNum` as needed
3. `CloseDOS()`

## Build linkage

When assembling/linking a HAS program that uses these functions, include `lib/dos.s` in your build alongside other used libraries. `lib/dos.s` is registered in `scripts/build_example.sh` (`LIB_SOURCES`/`ORDERED_LIBS` arrays).

## Runtime example

See `examples/dos_hello.has` for a complete non-bare-metal AmigaDOS CLI program using `InitDOS`, `PrintOut`, `PrintNum`, and `CloseDOS`.
