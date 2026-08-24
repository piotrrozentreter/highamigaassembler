# The `interrupt` / `starti` / `endi` keywords

Software VBlank dispatch slots for periodic (50Hz PAL / 60Hz NTSC) background
work, modeled on the AMOS Professional AMAL/`EVERY` channel system rather than
on a literal "16 CPU interrupt vectors" feature (the 68000 has no such thing -
see **Hardware model** below for the corrected facts).

## Syntax

```has
interrupt NAME(INDEX) -> void {
    // statements - no parameters, always void, no explicit return value
}

starti(INDEX);   // enable dispatch slot INDEX
endi(INDEX);     // disable dispatch slot INDEX
```

- `INDEX` is a compile-time integer literal, **0-15**.
- Each index may be declared by at most one `interrupt` proc in the program.
- `starti(X)`/`endi(X)` may appear in any proc body; the compiler checks that
  `X` was declared by an `interrupt` proc, and errors otherwise.

## Example

See [examples/interrupt_vbl_demo.has](../examples/interrupt_vbl_demo.has).

```has
extern func TakeSystem() -> void;
extern func ReleaseSystem() -> void;

bss counters:
    frame_count.l: 1

code main:
    asm { jmp main }

    interrupt vbl_counter(0) -> void {
        frame_count = frame_count + 1;
    }

    proc main() -> void {
        call TakeSystem();
        starti(0);
        // ... game loop ...
        endi(0);
        call ReleaseSystem();
        return;
    }
```

## Hardware model (and corrections to common assumptions)

The 68000 does **not** have "16 user interrupts". It has:
- 7 CPU priority levels (autovector interrupts 1-7, IPL0-2 lines) - not 16.
- 16 **software** trap vectors via `TRAP #0`-`TRAP #15` (vectors 32-47) - a
  different, unrelated mechanism (synchronous software traps, not periodic
  hardware interrupts).
- The 68000/68020 instruction to return from a real hardware/software
  exception is **`RTE`** ("ReTurn from Exception") - not `RTI` (that mnemonic
  is 6502/Z80 terminology, not 68k).

On the Amiga, periodic 50Hz/60Hz timing comes from a **single** hardware
source: the **VERTB** (vertical blank) interrupt, one bit (bit 5) of the
Paula/Agnus `INTENA`/`INTREQ` registers, routed through one CPU autovector
level. There is no hardware concept of "starting" or "stopping" one of 16
independent vectors - `INTENA`/`INTREQ` only have 14 real maskable source
bits total, and VERTB is just one of them.

Matching how AmigaOS's own `AddIntServer`/`SetIntVector` handlers work (and
how AMOS's AMAL/`EVERY` system works internally), this feature multiplexes
**16 software dispatch slots** off that single VERTB source:

1. The compiler auto-generates one hidden master VBlank ISR
   (`_has_vblank_isr`). On **every** `starti()` call, `_has_int_ensure_installed`
   checks whether the CPU's level-3 autovector ($6C) already points at this
   ISR; if not (first use, or after an intervening `ReleaseSystem()`/OS
   vector restore), it saves the current vector into `_has_old_vec3` and
   installs `_has_vblank_isr`. This check is self-correcting across repeated
   `TakeSystem()`/`starti()`/`ReleaseSystem()` cycles within one run.
2. `starti(X)` sets bit `X` in a 16-bit active-slot mask (`_has_int_mask`)
   and unmasks VERTB in `INTENA`. `endi(X)` clears bit `X`, and re-masks
   VERTB only once **no** slots remain active.
3. On every real VERTB interrupt, `_has_vblank_isr` acknowledges the
   interrupt, then walks the 16-slot dispatch table (`_has_int_slots`,
   `dc.l` per index, `0` for unused indices) and `jsr`s into every **active**
   slot in turn, finally executing a single `rte`.
4. Each `interrupt NAME(INDEX) -> void { ... }` proc is therefore a
   **dispatch slot**, not its own top-level exception handler: it still does
   a full `movem.l d0-d7/a0-a6,-(sp)` / `movem.l (sp)+,d0-d7/a0-a6` save and
   restore (as requested - no parameters, always void, no assumptions about
   caller-saved registers), but it must end in **`rts`** (it's `jsr`'d as a
   subroutine of the master ISR) - only the one hidden master ISR ends in
   `rte`. This exactly mirrors how real AmigaOS interrupt handlers/servers
   work (they also return via `RTS`, never `RTE` - only Exec's own installed
   autovector entry does that).

This design is deliberately **CPU-target-neutral**: no scaled/indexed
addressing or 68020-only instructions are used anywhere in the dispatch
loop or `starti`/`endi` codegen (plain `movem.l`/`bset`/`bclr`/`dbra`), so
the generated code is byte-identical in structure on both `--cpu 68000` and
`--cpu 68020` (only differs in that other, unrelated statements in the
interrupt proc body may use CPU-specific codegen as usual).

## Clean exit to DOS (`ReleaseSystem`)

`lib/takeover.s`'s `ReleaseSystem()` (paired with `TakeSystem()`) already
unconditionally clears **all** `INTENA`/`INTREQ` bits (`#$7fff`) before
restoring the OS's saved interrupt state, and now also saves/restores the
level-3 autovector (`$6C`, where this feature installs its master VBlank
ISR) alongside the pre-existing level-2/level-4 (`$68`/`$70`) save/restore.
This means calling `ReleaseSystem()` before returning to DOS always disables
VERTB and restores the original vector, regardless of whether the program
called `endi()` on every slot it `starti()`'d - a program that forgets to
`endi()` a slot still exits cleanly as long as it calls `ReleaseSystem()`.

**Mandatory ordering**: always call `TakeSystem()` before the *first*
`starti()` in the program. If `starti()` runs first, it installs
`_has_vblank_isr` into `$6C` and stashes the true original vector in its own
`_has_old_vec3` - a variable `TakeSystem()`/`ReleaseSystem()` don't know
about. A subsequent `TakeSystem()` call would then capture `_has_vblank_isr`
itself (not the real OS vector) into its `old_int3`, and `ReleaseSystem()`
would "restore" `$6C` right back to the (by-then-freed) interrupt handler
instead of the OS default - a dangling vector after the program exits.

## Restrictions

- No parameters (only the mandatory `(INDEX)` slot number).
- Must return `void`; `return <expr>;` inside an `interrupt` proc is a
  **compile error** (not just a warning, unlike a normal `void` proc).
- `starti(X)`/`endi(X)` with an out-of-range (`X` not in 0-15) or undeclared
  index is a compile error.
- Slot indices and names must be unique across the program.
- Interrupt procs cannot be `call`ed directly (they're not registered as
  normal callable procs) - they only run via the VBlank dispatcher.
