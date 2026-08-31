---
name: regression-sweep
description: 'Run HAS compiler regression validation: compile examples across both CPU targets, assemble with vasm, and diff generated .s output against a pre-change baseline. Use after any parser, validator, codegen, allocator, or peephole change to prove no regressions.'
argument-hint: 'State which compiler area changed and the depth wanted: smoke (5 examples), targeted (feature examples), or full (all examples, both CPU targets, baseline diff).'
user-invocable: true
---

# HAS Regression Sweep

Executable procedure for proving a compiler change did not regress anything. This repo has no single
"run all tests" command - correctness is established by compiling every example under both CPU targets
and diffing generated assembly against a baseline.

## Non-Negotiable Rules

1. **Both CPU targets, always.** `--cpu 68000` (default) and `--cpu 68020`. A change validated on one
   target is not validated.
2. **68000 output must stay byte-identical** unless the change is explicitly intended to alter it.
   The baseline diff below is how you prove that - not by reasoning about the code.
3. **Report per target.** Never collapse two targets into one pass/fail number.
4. **Compare against a known-failing set.** Some examples fail by design (negative fixtures, and
   `cpu68020_32bit_arithmetic.has`, which only compiles under `--cpu 68020`). Judge by *delta* from
   baseline, not by absolute zero failures.

## Platform Note

This repo is developed primarily on **Linux**; the `scripts/*.sh` build scripts are the canonical
tooling and have no PowerShell equivalents (only `scripts/tests/` has `.ps1` twins). Bash commands
below are authoritative. PowerShell equivalents are provided for Windows sessions - if the two ever
disagree, trust the bash form.

Interpreter: `python3` on Linux, `.venv\Scripts\python.exe` on Windows. Set `HASC_PYTHON` to override
(the `scripts/tests/` checkers honour it).

## Tier 1 - Smoke (fast, after any change)

```bash
PY=${HASC_PYTHON:-python3}
for cpu in 68000 68020; do
  for f in examples/add.has examples/calling_conventions.has examples/comprehensive_operators.has \
           examples/struct_pointer_test.has examples/wait_ms_demo.has; do
    "$PY" -m hasc.cli "$f" --cpu "$cpu" -o tmp/smoke.s >/dev/null 2>&1 || echo "FAIL $cpu $f"
  done
done
```

<details><summary>PowerShell</summary>

```powershell
$py = ".\.venv\Scripts\python.exe"
foreach ($cpu in @("68000","68020")) {
  foreach ($f in @("examples\add.has","examples\calling_conventions.has","examples\comprehensive_operators.has","examples\struct_pointer_test.has","examples\wait_ms_demo.has")) {
    & $py -m hasc.cli $f --cpu $cpu -o tmp\smoke.s 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { "FAIL $cpu $f" }
  }
}
```
</details>

## Tier 2 - Targeted

Compile the examples that exercise the changed subsystem, both targets, and read the generated `.s`.
Find them by feature keyword: `grep -rl "GetReg\|SetReg" examples/`.

Unit tests live in `tests/` and run under pytest (markers `runtime`, `musashi` per `pytest.ini`):

```bash
python3 -m pytest tests -q
```

The positive/negative example split checker (default CPU only, `examples/tests/compiler` only,
driven by the manifest `examples/tests/compiler/negative_examples.txt`):

```bash
bash scripts/tests/test_examples_split.sh        # Windows: .\scripts\tests\test_examples_split.ps1
```

Full link-level build of a single example (Linux-only, needs vasm+vlink):

```bash
bash scripts/build_example.sh examples/wait_ms_demo.has
```

## Tier 3 - Full Sweep (parser/validator/codegen/allocator/peephole changes)

110 example files (excluding `examples/includes/`, which are non-standalone snippets):

```bash
PY=${HASC_PYTHON:-python3}
mapfile -t files < <(find examples -name '*.has' -not -path 'examples/includes/*' | sort)
for cpu in 68000 68020; do
  fail=()
  for f in "${files[@]}"; do
    "$PY" -m hasc.cli "$f" --cpu "$cpu" -o tmp/sweep.s >/dev/null 2>&1 || fail+=("$f")
  done
  echo "cpu $cpu: total=${#files[@]} failed=${#fail[@]}"
  printf '  %s\n' "${fail[@]}"
done
```

<details><summary>PowerShell</summary>

```powershell
$py = ".\.venv\Scripts\python.exe"
$files = Get-ChildItem -Path examples -Recurse -Filter *.has | Where-Object { $_.FullName -notmatch '\\includes\\' } | Sort-Object FullName
foreach ($cpu in @("68000","68020")) {
  $fail = @()
  foreach ($f in $files) {
    & $py -m hasc.cli $f.FullName --cpu $cpu -o tmp\sweep.s 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { $fail += $f.Name }
  }
  "cpu ${cpu}: total=$($files.Count) failed=$($fail.Count)"
  $fail
}
```
</details>

## Baseline Diff (the decisive check)

Proves exactly which examples' generated assembly changed, and that nothing else moved.

```bash
git worktree add ../has-baseline HEAD
root=$PWD
for cpu in 68000 68020; do
  for tree in "$root" "$root/../has-baseline"; do
    tag=$([ "$tree" = "$root" ] && echo new || echo old)
    out="$root/tmp/out-$tag-$cpu"; mkdir -p "$out"
    ( cd "$tree" && find examples -name '*.has' -not -path 'examples/includes/*' | sort |
      while read -r f; do
        python3 -m hasc.cli "$f" --cpu "$cpu" -o "$out/$(basename "$f" .has).s" >/dev/null 2>&1
      done )
  done
  echo "=== cpu $cpu ==="
  diff -rq "tmp/out-old-$cpu" "tmp/out-new-$cpu"
done
git worktree remove ../has-baseline --force
```

<details><summary>PowerShell</summary>

```powershell
git worktree add ..\has-baseline HEAD
$root = $PWD.Path
foreach ($cpu in @("68000","68020")) {
  foreach ($tree in @($root, (Join-Path $root "..\has-baseline"))) {
    $tag = if ($tree -eq $root) { "new" } else { "old" }
    $out = Join-Path $root "tmp\out-$tag-$cpu"
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    Push-Location $tree
    Get-ChildItem -Path examples -Recurse -Filter *.has | Where-Object { $_.FullName -notmatch '\\includes\\' } | ForEach-Object {
      & ".\.venv\Scripts\python.exe" -m hasc.cli $_.FullName --cpu $cpu -o (Join-Path $out ($_.BaseName + ".s")) 2>&1 | Out-Null
    }
    Pop-Location
  }
  "=== cpu $cpu changed files ==="
  Get-ChildItem "tmp\out-new-$cpu" | ForEach-Object {
    $old = "tmp\out-old-$cpu\$($_.Name)"
    if ((Test-Path $old) -and (Get-FileHash $old).Hash -ne (Get-FileHash $_.FullName).Hash) { $_.Name }
  }
}
git worktree remove ..\has-baseline --force
```
</details>

Then inspect each changed file with
`git diff --no-index tmp/out-old-68000/X.s tmp/out-new-68000/X.s` and justify every hunk.
Unjustified diffs are regressions.

## Assembly Validation

Match the flag to the target:

```bash
vasmm68k_mot -m68000 -Fhunkexe -o tmp/test.o tmp/out-new-68000/add.s
vasmm68k_mot -m68020 -Fhunkexe -o tmp/test.o tmp/out-new-68020/add.s
```

Never validate 68000-targeted output with `-m68020` - that hides genuine 68020-only-instruction leaks
(`muls.l`, `divsl.l`, `extb.l`, scaled-index operands) into the 68000 path. vlink is silent on success.

Toolchain location: on PATH on Linux. On this Windows box also on PATH, or at
`C:\Users\prozentreter\Documents\vbcc_win_x64\vbcc\bin\vasmm68k_mot.exe`. Verify with
`command -v vasmm68k_mot` / `Get-Command vasmm68k_mot` rather than assuming either way.

**Windows-only trap when running `scripts/*.sh` under Git Bash**: `bash scripts/build_example.sh`
silently reports "Libs: (none auto-detected)" for every example if System32's `sort.exe` (which has
no `-u`) shadows GNU sort. `/usr/bin` must precede System32 on PATH.

## Reporting Contract

- Pass/fail counts **per CPU target**, plus the delta vs. baseline failure set.
- List of examples whose generated `.s` changed, with a one-line justification each.
- Whether vasm validation ran, per target, or why it was skipped.
- Any example that exercises the change on only one CPU target - flag as residual risk.

## References

- Delegated tiered testing agent: [../../agents/tests.agent.md](../../agents/tests.agent.md)
- Assembly correctness review: [../assembly-validator/SKILL.md](../assembly-validator/SKILL.md)
- Runtime emulation: `docs/MUSASHI_RUNTIME_TESTING.md`, `scripts/test_runtime_musashi.sh`
