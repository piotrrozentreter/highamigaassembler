# Compile-Time Python Integration

HAS supports two forms of compile-time Python code generation:

- **External generation with `--generate`** produces an entire HAS source file on standard output before parsing begins.
- **Inline `@python` directives** produce one or more statements inside the current procedure during code generation.

Both mechanisms run Python on the compiler host. They are code-generation tools, not runtime Python support in the generated Amiga program.

## Choosing a Mechanism

| Need | Use |
|---|---|
| Generate data sections, constants, procedures, or a complete program | External `--generate` |
| Read JSON, images, maps, or other build-time assets | External `--generate` |
| Inspect generated HAS source as a separate debugging step | External `--generate` |
| Calculate and insert statements inside one existing procedure | Inline `@python` |
| Unroll a small, fixed sequence using the current parameters or locals | Inline `@python` |

Use external generation for whole-file structure and asset pipelines. Use inline generation for small procedure-local expansions. Inline directives cannot add top-level data sections, constants, or procedure declarations.

## External Generation with `--generate`

The command-line form is:

```powershell
python -m hasc.cli ignored.has --generate generator.py -o output.s
```

The positional input argument is still required by the CLI, but its contents are **ignored** when `--generate` is present. The file does not need to exist. HAS runs the generator as:

```text
[sys.executable, script]
```

The generator receives no additional CLI arguments from HAS. It has 30 seconds to finish. HAS captures its complete standard output and treats it as the complete HAS source, then runs the normal parser, validator, unused-procedure handling, and code generator. A nonzero exit code or timeout stops compilation.

Because stdout is the source channel, print only valid HAS source to stdout. Send diagnostics to stderr:

```python
import sys

print("loading level data", file=sys.stderr)
print("code generated:")
print("    proc start() -> int {")
print("        return 0;")
print("    }")
```

### Sine Lookup Table

This generator creates an unsigned 64-entry sine table suitable for game motion. Save it as `generate_sine.py`:

```python
import math

entries = 64
values = []

for index in range(entries):
    angle = index * 2.0 * math.pi / entries
    values.append(str(int(127 * math.sin(angle)) + 128))

print("data math_tables:")
print(f"    sin_table.b[{entries}] = {{ {', '.join(values)} }}")
print()
print("code generated:")
print("    proc start() -> int {")
print("        return 0;")
print("    }")
```

Compile it directly:

```powershell
python -m hasc.cli ignored.has --generate generate_sine.py -o sine_table.s
```

For debugging, first capture and inspect exactly what the compiler will parse:

```powershell
python generate_sine.py > generated_sine.has
python -m hasc.cli generated_sine.has -o sine_table.s
```

### Level and Tile Data from JSON

External generation is a good fit for converting level-editor output into static HAS arrays. This small example uses a flat tile list.

Save this as `level.json`:

```json
{
  "width": 4,
  "height": 3,
  "tiles": [0, 0, 1, 0, 2, 2, 1, 0, 0, 3, 3, 0]
}
```

Save this as `generate_level.py`:

```python
import json
import sys

with open("level.json", "r", encoding="utf-8") as level_file:
    level = json.load(level_file)

width = int(level["width"])
height = int(level["height"])
tiles = [int(tile) for tile in level["tiles"]]

if len(tiles) != width * height:
    raise ValueError("tile count does not match width * height")
if any(tile < 0 or tile > 255 for tile in tiles):
    raise ValueError("tile IDs must fit in a byte")

print(f"generating {width}x{height} level", file=sys.stderr)
print("data level_data:")
print(f"    level_width.w = {width}")
print(f"    level_height.w = {height}")
print(f"    level_tiles.b[{len(tiles)}] = {{ {', '.join(map(str, tiles))} }}")
print()
print("code generated:")
print("    proc start() -> int {")
print("        return 0;")
print("    }")
```

Run it from the directory containing both files:

```powershell
python -m hasc.cli ignored.has --generate generate_level.py -o level_data.s
```

The generator should validate asset shape and value ranges itself. HAS validates the generated HAS program, but it does not know the intended JSON schema.

## Inline `@python`

An inline directive appears where a statement is allowed inside a procedure. Python must assign generated HAS text to the name `generated_code`.

### String Syntax

Use a quoted Python program followed by a semicolon:

```has
code generated:
    proc calculated_assignment() -> int {
        var result:int = 0;

        @python "import math; angle = math.pi / 6; value = int(100 * math.sin(angle)); generated_code = f'result = {value};'";

        return result;
    }
```

### Block Syntax

Block syntax is easier to read for multiple Python statements:

```has
code generated:
    proc add_fixed_steps(step:int) -> int {
        var total:int = 0;

        @python {
lines = []
for index in range(4):
    lines.append("total = total + step;")
generated_code = lines
        }

        return total;
    }
```

Here `generated_code` is a list of four HAS assignment strings. A single string may also contain multiple statements. Generated statements are emitted in the current procedure context, so they can refer to its existing parameters and locals, such as `step` and `total` above.

Compile an inline source normally:

```powershell
python -m hasc.cli inline_generation.has -o inline_generation.s
```

### Python Environment

Inline code receives `math` directly and these selected builtins:

```text
range, len, list, dict, str, int, float, enumerate, zip,
sum, max, min, abs, round, pow
```

Imports are allowed through Python's normal `__import__`, so `import math`, `import json`, and other modules available to the selected interpreter can be used. Inline code has no HAS AST, validator, symbol-table, or compiler API. Its only output contract is the `generated_code` variable.

`generated_code` may be:

- A string containing one or more procedure statements.
- A list whose string elements each contain procedure statements.

If `generated_code` is not assigned, the directive emits nothing. If it has another type, or a list contains non-string elements, those values are silently ignored. Python exceptions and parse/code-generation failures are reported as `@python directive execution failed` code-generation errors.

## Validation and Structural Limits

Inline directives run during code generation, **after the original HAS module has completed semantic validation**. The generated text is parsed as the body of a temporary procedure and then emitted in the current procedure context, but those generated statements do not pass through the semantic validator.

Consequences include:

- Syntax errors in generated text are caught during code generation.
- Existing parameters and locals can be referenced because code generation receives the current procedure context.
- Undefined names, type mismatches, invalid calls, and other semantic mistakes may produce a later code-generation error or incorrect assembly instead of a normal validation diagnostic.
- Top-level constructs cannot be generated inline because the text is parsed only as procedure statements. Use `--generate` for data sections, constants, procedures, or complete modules.
- There is no API for querying HAS types or symbols from Python.

Keep inline expansions small and compile representative paths frequently. Prefer external generation when generated structure needs full normal validation.

## Debugging

For external generators:

1. Run `python generator.py > generated.has`.
2. Open `generated.has` and check that it is the complete intended source.
3. Compile it normally with `python -m hasc.cli generated.has -o generated.s`.
4. Keep progress messages, asset statistics, and debug prints on stderr with `print(..., file=sys.stderr)`.

For inline directives:

1. Build `generated_code` in a plainly named variable before assigning it.
2. Temporarily write that variable to stderr: `__import__('sys').stderr.write(output + '\n')`.
3. Paste the printed statements into the procedure and compile them normally when diagnosing parser or code-generation failures.
4. Check the final assembly, especially when generated statements depend on types or calling conventions, because semantic validation is not run on them.

External stdout must contain only HAS source. Inline stdout is not consumed as generated source, but stderr is still the clearest place for diagnostics.

## Security and Reproducibility

Only run trusted generators and inline directives. Python imports are unrestricted, so compile-time code can read or modify files, access the network, inspect environment variables, and execute other processes with the permissions of the compiler user. The selected-builtin dictionary is **not a security sandbox**.

For reproducible builds:

- Pin Python package versions used by generators.
- Resolve asset paths deliberately and run builds from a known working directory.
- Validate input schemas and numeric ranges in external generators.
- Avoid timestamps, random values, and machine-specific paths in generated output.
- Keep generators and source assets in version control.

## Current Limitations

- `--generate` still requires a positional input argument and ignores it.
- HAS passes no generator-specific CLI arguments to an external script.
- External generation is limited to 30 seconds.
- External stdout replaces the entire HAS input; it is not merged with the positional file.
- Inline Python can generate only procedure statements, not top-level declarations.
- Inline Python has no HAS AST, type, symbol, or source-location API.
- Missing or unsupported `generated_code` values silently emit no statements.
- Inline generated statements are parsed but not semantically validated.

## Existing Examples

- [`examples/code_generator.py`](../examples/code_generator.py) generates lookup arrays and complete procedures for the external workflow.
- [`examples/python_directive.has`](../examples/python_directive.has) demonstrates the inline string form and a calculated assignment.

Run the existing examples on Windows with:

```powershell
python -m hasc.cli ignored.has --generate examples/code_generator.py -o generated_example.s
python -m hasc.cli examples/python_directive.has -o inline_example.s
```
