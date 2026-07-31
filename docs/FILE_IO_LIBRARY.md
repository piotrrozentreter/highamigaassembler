# File I/O Library (`lib/fileio.s`)

`lib/fileio.s` provides thin wrappers for AmigaDOS file operations so HAS programs can read and write files using normal `extern func` calls.

## Safety model with takeover

If your program uses `TakeSystem()`, do not call DOS APIs while takeover is active.

Safe pattern:

1. `ReleaseSystem()`
2. `FileIoInit()` and file operations
3. `FileIoDone()`
4. `TakeSystem()`

See also the runtime example in `examples/fileio_demo.has`.

## Include declarations

Use:

```has
#include "includes/fileio_defs.has";
```

This include provides constants and `extern func` declarations for all exported symbols.

## API reference

### `FileIoInit() -> int`

Opens `dos.library` and caches its base.

- Returns `0` on success.
- Returns `-1` on failure.
- Idempotent: if already initialized, returns success without reopening.

### `FileIoDone() -> int`

Closes cached `dos.library` base if open.

- Returns `0`.
- Idempotent: safe to call even when not initialized.

### `FileIoErr() -> int`

Returns the DOS `IoErr()` code for the most recent failure.

- Returns DOS error code on success.
- Returns `-1` if `FileIoInit()` was not called.

Call this immediately after a failed `FileOpen`/`FileRead`/`FileWrite`/`FileSeek`/`FileClose` for best diagnostics.

### `FileOpen(path: ptr, mode: int) -> int`

Calls DOS `Open()`.

- `path`: pointer to NUL-terminated path string.
- `mode`: one of `DOS_MODE_READWRITE`, `DOS_MODE_OLDFILE`, `DOS_MODE_NEWFILE`.
- Returns file handle (BPTR) on success, `0` on failure.

### `FileClose(handle: int) -> int`

Calls DOS `Close()`.

- Returns DOS close result (non-zero for success in classic DOS style).

### `FileRead(handle: int, buffer: ptr, length: int) -> int`

Calls DOS `Read()`.

- Returns bytes read on success.
- Returns `-1` on failure.

### `FileWrite(handle: int, buffer: ptr, length: int) -> int`

Calls DOS `Write()`.

- Returns bytes written on success.
- Returns `-1` on failure.

### `FileSeek(handle: int, position: int, mode: int) -> int`

Calls DOS `Seek()`.

- `mode`: one of `DOS_OFFSET_BEGINNING`, `DOS_OFFSET_CURRENT`, `DOS_OFFSET_END`.
- Returns previous file position on success.
- Returns `-1` on failure.

## Build linkage

When assembling/linking a HAS program that uses these functions, include `lib/fileio.s` in your build alongside other used libraries.
