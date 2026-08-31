---
name: has-language
description: 'HAS source language syntax reference. Use when writing, reading, or fixing .has files - proc/func declarations, data/bss sections, BASIC-style for loops, structs, inline asm blocks, preprocessor directives - or when a .has file fails to parse with a Lark syntax error.'
argument-hint: 'Describe the .has construct you need (e.g. "declare a struct array in bss", "why does this for loop not parse") or paste the failing source and error.'
user-invocable: true
---

# HAS Language Syntax

HAS looks C-like but is **not C**. Several constructs that look obviously valid are rejected by the
grammar, and several C habits silently compile into something different. Consult
[syntax-cheatsheet.md](./references/syntax-cheatsheet.md) before writing any `.has` file from scratch.

## When to Use

- Writing a new `.has` example, demo, or throwaway probe file.
- A `.has` file fails with a Lark parse error ("No terminal matches ...", "Unexpected token ...").
- Reviewing whether generated/edited HAS source uses real language features vs. invented ones.
- Deciding whether a compiler feature needs new grammar or already has syntax.

## Non-Negotiable Rules

1. **Ground claims in the grammar.** The single source of truth is the `GRAMMAR` string at the top of
   `hasc/parser.py`. If unsure whether a construct exists, grep that string - do not infer from C,
   from docs, or from another dialect.
2. **No implicit entry point.** Execution starts at the first instruction emitted in the `code`
   section, which in practice means an `asm { }` block. A `proc main()` that nothing jumps to never runs.
3. **Locals are scalars only.** `var NAME: TYPE;` where `type: CNAME STAR?`. There is no local array
   or local struct-instance declaration syntax - aggregates live in `data`/`bss` sections.
4. **Prefer copying a working example** over writing from memory. `examples/` has 100+ verified files.

## Procedure

1. Identify the construct category (top-level item, section content, statement, expression).
2. Check [syntax-cheatsheet.md](./references/syntax-cheatsheet.md) for the verified form.
3. If the construct is not listed, grep `hasc/parser.py`'s `GRAMMAR` for the keyword before assuming
   it is unsupported - the cheatsheet covers common cases, not every rule.
4. Write the file, then compile it to confirm: `python3 -m hasc.cli FILE.has -o tmp/probe.s`
   (Windows: `.\.venv\Scripts\python.exe`).
5. For any codegen-relevant construct, also compile with `--cpu 68020` (see the `regression-sweep` skill).

## File Encoding Gotcha

The HAS lexer rejects a UTF-8 BOM ("No terminal matches '' ... at line 1 col 1"). This is a
**Windows-only** hazard: PowerShell's `Set-Content -Encoding utf8` writes a BOM. Standard Linux
tooling (`cat > file`, heredocs, editors) does not. On Windows, create `.has` files with the editing
tools, or with:

```powershell
[System.IO.File]::WriteAllText($path, $content, (New-Object System.Text.UTF8Encoding $false))
```

## References

- Verified syntax cheat sheet: [syntax-cheatsheet.md](./references/syntax-cheatsheet.md)
- Example authoring conventions: [../../instructions/has-examples.instructions.md](../../instructions/has-examples.instructions.md)
- Grammar source of truth: `hasc/parser.py` (`GRAMMAR`)
