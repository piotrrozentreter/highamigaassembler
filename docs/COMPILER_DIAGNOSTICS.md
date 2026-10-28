# Compiler Warnings and Errors

This reference catalogs compiler-authored diagnostics in `hasc/`, including
preprocessing, asset imports, parsing, semantic validation, code generation,
register allocation, and optional assembler/linker/ADF orchestration. It describes
the current implementation, not proposed fixes. Unless explicitly marked otherwise,
the checks are shared by `--cpu 68000` (default) and `--cpu 68020`.

Message templates use `{placeholders}` for names, values, paths, exception text,
or computed details. Repeated emission sites are grouped, but distinct messages
are retained. Source links point to the checks or message builders; line numbers
can move as the compiler evolves.

## Reading a Diagnostic

- **Error:** stops the affected compilation/build stage. Validator errors are
  usually accumulated into `Validation failed:`; other stages usually stop at
  the first exception. No successful executable build is implied by an existing
  `.s` file.
- **Warning:** compilation can continue. A warning is not necessarily proof of
  incorrect code. Validator warnings collected in a failing validation run are
  not returned to the CLI; explicit warning directives print immediately.
- **Internal diagnostic:** a compiler invariant or unsupported AST state failed.
  First retry with validation enabled, then reduce the source and report a
  compiler bug with CPU target, command, source, and full diagnostic.
- **External/dependency exception:** Python, Lark, Pillow, XML/JSON readers,
  filesystem calls, user Python, vasm, vlink, and amitools can supply additional
  text or tracebacks. Their version/platform/input-dependent messages are not
  a finite compiler-authored catalog. HAS wrappers are listed below; their
  `{exception}`, `{stderr}`, and `{stdout}` contents are not fixed HAS messages.

`--no-validate` skips semantic validation, including its warnings and `#error`
handling; it is not a remedy for an invalid program. The CLI normally exits 1
for caught compilation/build errors; argument parsing is handled by argparse.
See [CLI stage handling](../hasc/cli.py#L225).

## CLI and Stage Wrappers

These are errors unless marked otherwise. See
[CLI arguments](../hasc/cli.py#L121) for argparse-defined options.

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `Error: Generation script failed with code {returncode}`; `stderr: {stderr}` | `--generate` subprocess returned nonzero. Run/debug that script with the same Python; its stdout must be HAS source. Child stderr is external text. | [cli.py](../hasc/cli.py#L198), [stderr](../hasc/cli.py#L200) |
| `Error: Generation script timed out (30 seconds)` | Generator exceeded the fixed timeout. Remove hangs or reduce its work. | [cli.py](../hasc/cli.py#L205) |
| `Error: Generation script not found: {generate}` | The subprocess launch raised `FileNotFoundError`. Check the generator and Python executable; a missing script commonly instead produces Python stderr and a nonzero exit. | [cli.py](../hasc/cli.py#L208) |
| `Error: Failed to run generation script: {exception}` | Other generator-launch failure. Check permissions, interpreter and exception details. | [cli.py](../hasc/cli.py#L211) |
| `Error: Input file not found: {input}` | Missing input. Correct the path/current directory. | [cli.py](../hasc/cli.py#L219) |
| `Error: Failed to read input file: {exception}` | Input I/O failure. Check permissions and filesystem; UTF-8 decoding failures can escape this `IOError` handler. | [cli.py](../hasc/cli.py#L222) |
| `Error in {input}:` | HAS `SyntaxError` from preprocessing/parsing, followed by its message. Fix the nested diagnostic below. | [cli.py](../hasc/cli.py#L236) |
| `Syntax error in {input}:` | Escaping Lark unexpected-input exception. Fix the reported grammar/token location. | [cli.py](../hasc/cli.py#L240) |
| `Parse error in {input}:` | Other Lark error, including transformer failures not translated to HAS syntax errors. Inspect the nested rule/exception. | [cli.py](../hasc/cli.py#L244) |
| `Warning: {warning}` | Warning returned after successful validation. Review the warning rather than automatically changing code. | [cli.py](../hasc/cli.py#L257) |
| `Validation error in {input}:`; `Validation failed:\n{errors}` | Semantic checks failed. Correct all listed errors before retrying. | [cli.py](../hasc/cli.py#L259), [validator.py](../hasc/validator.py#L221) |
| `Code generation error in {input}:` | `CodeGenError` during `gen()`. Follow the nested message; constructor/helper exceptions outside this handler may instead produce tracebacks. | [cli.py](../hasc/cli.py#L290) |
| `Error: {exception}` | Optional executable/ADF build raised `ToolchainError`. See toolchain diagnostics. Assembly may already have been written. | [cli.py](../hasc/cli.py#L318) |

Argparse produces its own usage/errors for missing input, unknown arguments,
invalid `--cpu` choices, and missing option values. Python import errors before
`main()` (for example missing Lark), uncaught output-write errors, and other
uncaught exceptions can print Python tracebacks. These are dependency/runtime
diagnostics, not additional fixed HAS templates. Install the project requirements,
check UTF-8 input, output parent directories and permissions as appropriate.
`Generating code`, `Generated ... bytes`, `Wrote ...`, build statistics,
`Strip report: top-level asm block detected; keeping all internal procedures`,
and strip roots/kept/removed reports are informational, not warnings or errors.

## Preprocessor and Parser

### Conditional Directives, Constants and Includes

Except where shown otherwise, the following error bodies are prefixed
`Preprocessor error at line {line_no}:`.

| Message body | Cause and practical remedy | Source |
| --- | --- | --- |
| `invalid token in const expression near '{bad}'` | Unrecognized expression character/token. Use supported constant-expression syntax. | [parser.py](../hasc/parser.py#L1364) |
| `empty const expression` | Expression has no tokens. Supply a value. | [parser.py](../hasc/parser.py#L1373) |
| `incomplete const expression` | Operand is missing. Complete the expression. | [parser.py](../hasc/parser.py#L1428) |
| `missing ')' in const expression` | Unbalanced expression parentheses. Add the closing parenthesis. | [parser.py](../hasc/parser.py#L1433) |
| `unsupported token '{tok}' in const expression` | Token cannot start the expected expression. Replace it with a supported operand/operator. | [parser.py](../hasc/parser.py#L1439) |
| `unexpected token '{token}' in const expression` | Tokens remain after expression evaluation. Remove trailing syntax or supply the missing operator. | [parser.py](../hasc/parser.py#L1448) |
| `'#{kind}' requires a name` | Empty `#ifdef`/`#ifndef`. Supply an identifier. | [parser.py](../hasc/parser.py#L1484) |
| `invalid identifier '{arg}' in '#{kind}'` | Conditional name is not an identifier. Use one name, not an expression. | [parser.py](../hasc/parser.py#L1486) |
| `'#if' requires a condition` | No condition. Supply `IDENT OP EXPR`. | [parser.py](../hasc/parser.py#L1513) |
| `'#if' condition '{arg}' must be 'IDENT OP EXPR' (operators: ==, !=, <>, >, <, >=, <=)` | Unsupported conditional shape. Use a named constant and a listed comparison. | [parser.py](../hasc/parser.py#L1519) |
| `'#if' condition for '{name}' is missing a right-hand side expression` | Comparison lacks a value. Add its right operand. | [parser.py](../hasc/parser.py#L1525) |
| `undefined constant '{name}' used in '#if' condition` | Conditional constant is unavailable. Define it before use or correct its name. | [parser.py](../hasc/parser.py#L1546) |
| `'#else' without matching '#ifdef/#ifndef/#if'` | Unmatched else. Restore conditional nesting. | [parser.py](../hasc/parser.py#L1580) |
| `multiple '#else' for conditional opened at line {line_opened}` | Duplicate else. Keep one else per conditional. | [parser.py](../hasc/parser.py#L1585) |
| `'#endif' without matching '#ifdef/#ifndef/#if'` | Extra closing directive. Restore conditional nesting. | [parser.py](../hasc/parser.py#L1596) |
| `Preprocessor error: unterminated '#{kind} {name}' opened at line {line_opened} (missing '#endif')` (full message) | End of input with an open conditional. Close it with `#endif`. | [parser.py](../hasc/parser.py#L1687) |
| `#include cycle detected for {inc_path}` (full message) | Recursive include dependency. Break the cycle or guard the headers. | [parser.py](../hasc/parser.py#L1615) |
| `#include: file not found: {inc_path}` (full message) | Include resolution found no file. Correct the path relative to the including source. | [parser.py](../hasc/parser.py#L1620) |
| `#include: failed to read {inc_path}: {exception}` (full message) | Include read/decode failure. Check permissions, encoding and path. | [parser.py](../hasc/parser.py#L1622) |
| `{exception}` | Constant pre-evaluation failed with `ValueError`; the line prefix is added. Correct the expression, particularly zero divisors. | [parser.py](../hasc/parser.py#L1653) |

Constant evaluation also authors `Unknown constant '{name}'`,
`Division by zero in constant expression`, and
`Modulo by zero in constant expression`. Define constants before use and use
nonzero divisors. These can be wrapped as
`Constant expression error{const_prefix} at line {line}, column {column}: {original}`
or `Constant expression error{const_prefix}: {original}`;
`const_prefix` is either empty or ` in const '{const_name}'`.
Sources: [unknown constant](../hasc/parser.py#L327),
[division](../hasc/parser.py#L341), [modulo](../hasc/parser.py#L349),
[pre-evaluation division](../hasc/parser.py#L1408),
[pre-evaluation modulo](../hasc/parser.py#L1415),
[located wrapper](../hasc/parser.py#L1897), [fallback wrapper](../hasc/parser.py#L1900).

### Syntax Formatting and Internal Parser Checks

The [syntax formatter](../hasc/parser.py#L1850) produces:

```text
Syntax error at line {line}, column {column}: Unexpected token '{token_val}'
Syntax error at line {line}, column {column}: Unexpected end of input
```

It can append `. Expected one of: {tokens}` (up to eight human-readable token
names, then `, ...`), the source line, a caret, and `Hint: {hint}`. The translation
to `SyntaxError` is at [parser.py](../hasc/parser.py#L1884). Fix the earliest
unexpected token and inspect preceding delimiters; later syntax errors may be
consequences. Hint strings are cataloged with their checks below.

| Hint | Trigger and remedy | Source |
| --- | --- | --- |
| `Did you forget ':' after section name?` | Only a colon is expected. Add the section colon. | [parser.py](../hasc/parser.py#L1821) |
| `Missing expression after '='.` | Semicolon encountered where several expression starters are expected. Supply the initializer/expression. | [parser.py](../hasc/parser.py#L1824) |
| `Missing ';' at the end of the previous statement.` | A new statement/name appears where a semicolon is expected. Terminate the preceding statement. | [parser.py](../hasc/parser.py#L1827) |
| `Missing ')' before '{'.` | Opening brace encountered while expecting a closing parenthesis. Close the condition/signature first. | [parser.py](../hasc/parser.py#L1830) |
| `Missing closing '}' for a block.` | End token while a closing brace is expected. Close the block. | [parser.py](../hasc/parser.py#L1833) |
| `Incomplete comparison expression inside parentheses.` | Closing parenthesis follows a comparison operator. Supply the right operand. | [parser.py](../hasc/parser.py#L1841) |
| `Top-level variable declarations are not allowed in code sections. Use data/bss or local 'var' inside a procedure.` | Unexpected `var`. Move storage to data/BSS or inside a procedure. | [parser.py](../hasc/parser.py#L1844) |
| `Unexpected end of input.` | Empty end token. Complete the missing statement/block. | [parser.py](../hasc/parser.py#L1847) |

Internal parser diagnostics:

- **Warning:** `[HAS parser warning] stmt_block: {count} None statements filtered out. Possible parser bug or unhandled construct.`
  The block transformer dropped `None` entries. Check the construct and report
  a reduced reproduction; do not assume all statements were compiled.
  [Source](../hasc/parser.py#L1067).
- **Error:** `compound_assign_stmt: expected 3 items, got {count}: {items}`.
  Unexpected transformer shape. Report the compound assignment and full Lark
  wrapper rather than treating this as a normal type error.
  [Source](../hasc/parser.py#L955).

## Validator Warnings

| Message | Trigger and practical remedy | Source |
| --- | --- | --- |
| `Warning: {message}` | A source `#warning` directive. User-authored message, printed immediately to stdout during validation. Inspect the directive and its condition. | [validator.py](../hasc/validator.py#L42) |
| `Unknown pragma: {name}` | Pragma other than `lockreg` or `strict16arith`. Correct the name or remove an unsupported pragma. | [validator.py](../hasc/validator.py#L358) |
| `In proc '{proc}': Empty return in non-void function` | Bare return in a procedure with a known non-void return type. Return the required value or correct the signature. | [validator.py](../hasc/validator.py#L678) |
| `In proc '{proc}': Return with value in void function` | Value returned from an ordinary void procedure. Remove the value or correct the signature; interrupt procedures instead receive an error. | [validator.py](../hasc/validator.py#L688) |
| `In proc '{proc}': Argument '{arg}' to '{callee}' parameter '{param}' looks like it expects a pointer. Did you mean '&{arg}'?` | Name-based heuristic, **not proof of a pointer mismatch**. See the important qualification below. | [validator.py](../hasc/validator.py#L979) |

### Pointer-Parameter Warning: Do Not Blindly Add `&`

The current [_check_pointer_parameter_matches](../hasc/validator.py#L954)
checks paired arguments/parameters only when there are call arguments:

1. The **parameter name contains `ptr`, case-insensitively**. It does not
   establish pointer intent from the parameter's declared type.
2. The argument is a **bare `VarRef`**, not address-of, an indexed expression,
   or another expression.
3. If the argument's type recorded in the supplied symbol table satisfies
   `ast.is_pointer`, it is **exempt**. Explicitly pointer-typed locals and
   parameters therefore do not need `&`. Globals/externs are recorded with
   generic symbol markers, so the exemption is not general value-flow analysis.

The helper is invoked for [call statements](../hasc/validator.py#L737) and
[call expressions](../hasc/validator.py#L934); the `MacroCall` procedure-call
fallback does not invoke it. Its coverage is not a full pointer type checker.

An integer can legitimately hold a heap address. **`HeapFree(score_str)` and
`HeapFree(numstr)` are correct when those integers hold the heap addresses to
free.** `&score_str` or `&numstr` passes the address of the variable's storage,
not the heap address stored in it. That change can free the wrong address.
Check the callee contract and where the value came from. Add `&` only when
the callee really needs the storage address; use an explicit pointer type where
the API and language permit it. This documents the current heuristic and its
false positives; it does **not** claim the warning has been fixed.

## Validator Errors

Unless a row states otherwise, procedure-local messages begin
`In proc '{proc}': `. The validator checks names and selected semantics, not
every possible runtime error or all assembly validity.

### Directives, Declarations and Data

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `Error: {message}` | Explicit source `#error`; immediate `ValidationError`, not an accumulated error. Resolve the condition or issue described by the source author. | [validator.py](../hasc/validator.py#L45) |
| `Macro '{name}' already defined` | Duplicate macro. Rename/remove the duplicate or correct include guards. | [module](../hasc/validator.py#L52), [code section](../hasc/validator.py#L151) |
| `Constant '{name}' already declared` | Duplicate constant across module/data/BSS declarations. Keep one definition. | [module](../hasc/validator.py#L58), [data](../hasc/validator.py#L66), [BSS](../hasc/validator.py#L99) |
| `Array '{name}' declared with length {declared_length} but has {actual_length} initializer values` | Too many values in a checked 1D initializer; strings contribute their character count. Reduce values or increase the declared length. Underfill is permitted. | [validator.py](../hasc/validator.py#L83) |
| `Duplicate #import label '{symbol}'` | Reused imported label. Give imports distinct labels. | [validator.py](../hasc/validator.py#L185) |
| `Imported asset label '{symbol}' conflicts with an existing symbol` | Import collides with a global, extern, procedure, macro or constant. Rename one symbol. | [validator.py](../hasc/validator.py#L196) |
| `Array dimension constant '{dimension}' not defined for '{name}'` | Unresolved dimension. Declare the constant or use a numeric dimension. | [validator.py](../hasc/validator.py#L258) |
| `Size constant '{size}' not defined for '{name}'` | Unresolved BSS size. Define/correct the constant. | [validator.py](../hasc/validator.py#L277) |
| `Unknown type '{type}' for struct field '{struct}.{field}'{where}` | Typed field uses an unknown type; optional ` (line {line})`. Use a supported field type. | [validator.py](../hasc/validator.py#L298) |
| `Type '{type}' is not a valid struct field type for '{struct}.{field}'{where}` | Field type is void or not 1, 2 or 4 bytes. Use a supported scalar/pointer field. | [validator.py](../hasc/validator.py#L303) |
| `Pragma lockreg: Invalid register '{reg}'. Valid registers: d0-d7, a0-a7` | Invalid register spelling. Choose a listed, non-reserved register. | [validator.py](../hasc/validator.py#L347) |
| `Pragma lockreg: Cannot lock reserved register '{reg}'` | Lock request uses `d7`, `a6` or `a7`. Leave loop/frame/stack registers available. | [validator.py](../hasc/validator.py#L349) |
| `Pragma strict16arith: Expected exactly one argument: on or off` | Wrong pragma arity. Supply one mode. | [validator.py](../hasc/validator.py#L352) |
| `Pragma strict16arith: Invalid mode. Use on or off` | Unsupported mode. Use `on` or `off`. | [validator.py](../hasc/validator.py#L356) |
| `In extern func '{name}': Parameter '{param}' cannot use reserved register '{reg}'` | Extern parameter assigned `a6`/`a7`. Correct the ABI declaration; do not change it independently of the callee. | [validator.py](../hasc/validator.py#L376) |
| `In extern func '{name}': Register '{reg}' is assigned to multiple parameters` | Duplicate parameter register. Match distinct registers to the real ABI. | [validator.py](../hasc/validator.py#L381) |
| `In native proc '{proc}': Parameter '{param}' must use __reg. Native functions require all parameters to be register-based.` | Native parameter lacks a register annotation. Specify its ABI register or use a non-native procedure. | [validator.py](../hasc/validator.py#L419) |
| `In native proc '{proc}': Local variables are not allowed. Native functions cannot allocate stack space for local variables.` | Native body declares a local, including nested blocks. Remove stack locals or make the procedure non-native. | [validator.py](../hasc/validator.py#L461) |
| `Variable '{name}' already declared` | Local duplicates a parameter or collected local in the procedure. Rename/remove it. | [validator.py](../hasc/validator.py#L487) |

### Statements, Calls and Expressions

| Message body (after procedure prefix) | Cause and practical remedy | Source |
| --- | --- | --- |
| `{count} PUSH(es) without matching POP(s)` | Register-save balance is not restored. Pair saves/restores on the intended paths. | [validator.py](../hasc/validator.py#L529) |
| `POP() without matching PUSH()` | Restore with no tracked save. Remove it or add the corresponding save. | [validator.py](../hasc/validator.py#L546) |
| `Undefined array '{name}'` | Assignment target array is unknown. Declare it or correct the name. | [validator.py](../hasc/validator.py#L633) |
| `Undefined struct variable '{name}'` | Member-access base is unknown. Declare it or correct the name. | [assignment](../hasc/validator.py#L645), [expression](../hasc/validator.py#L852) |
| `Undefined struct array '{name}'` | Indexed member-access base is unknown. Declare it or correct the name. | [assignment](../hasc/validator.py#L651), [expression](../hasc/validator.py#L858) |
| `Unsupported member assignment target` | Member base is not a supported variable, indexed array or dereferenced pointer. Rewrite using a supported base. | [validator.py](../hasc/validator.py#L661) |
| `Undefined variable '{name}'` | Unknown assignment target or expression name. Declare/correct it or include its declaration. | [assignment](../hasc/validator.py#L666), [expression](../hasc/validator.py#L837) |
| `Undefined function '{name}'` | Unknown call statement. Declare/define/include the function. | [validator.py](../hasc/validator.py#L723) |
| `Call to '{name}' expects {expected} argument(s), got {actual}` | Call arity differs from declaration. Match the signature and verify the included header. | [call](../hasc/validator.py#L732), [fallback](../hasc/validator.py#L762), [expression](../hasc/validator.py#L927) |
| `Macro '{name}' expects {expected} argument(s), got {actual}` | Macro arity mismatch. Supply the declared parameters. | [validator.py](../hasc/validator.py#L752) |
| `Undefined macro or function '{name}'` | Neither macro nor function is known. Correct spelling or declaration; optional `. Did you mean: {up_to_three_names}?` lists heuristic suggestions. | [validator.py](../hasc/validator.py#L775) |
| `Cannot index through 'void*' variable '{name}': the element size is undefined. Declare it with a concrete element type (e.g. 'byte*', 'int*').` | Indexing has no element stride. Use the actual concrete pointer type. | [validator.py](../hasc/validator.py#L801) |
| `Cannot index '{name}[...]' directly: '{name}' was declared with the bss 'name.suffix: COUNT' form, which reserves raw storage but is not a real array (indexing it would read whatever bytes live there as a pointer). Declare it as '{name}.suffix[COUNT]' (bracket-dims form) for direct element indexing instead.` | Raw BSS storage with count greater than one is indexed as though it were an array. Use bracket dimensions for real array storage. | [validator.py](../hasc/validator.py#L807) |
| `countdown until (...) requires a comparison (==, !=, <, <=, >, >=); got {node_type}`; optional ` with op {operator!r}` | Unsupported countdown condition. Use one simple relational/equality comparison. | [validator.py](../hasc/validator.py#L819) |
| `Unsupported member access base in expression` | Unsupported base AST for a member read. Use a named struct, indexed struct array or typed dereferenced pointer. | [validator.py](../hasc/validator.py#L868) |
| `Undefined variable '{name}' in address-of expression` | Unknown `&name`. Declare the storage first. | [validator.py](../hasc/validator.py#L882) |
| `Undefined array '{name}' in address-of expression` | Unknown `&name[index]`. Declare/correct the array. | [validator.py](../hasc/validator.py#L889) |
| `Cannot take address of non-variable expression` | Address-of applied to an unsupported non-storage expression. Use a supported variable or indexed element. | [validator.py](../hasc/validator.py#L896) |
| `Undefined function '{name}' in expression` | Expression calls an unknown function. Declare it. Optional suffix: ` (note: '{name}' is a macro, not a function - macros cannot be used in expressions)` or `. Did you mean: {up_to_three_names}?`. Use a real value-returning function, not an assembly macro. | [validator.py](../hasc/validator.py#L920) |
| `GetReg invalid register '{register}'. Valid registers: d0-d7, a0-a3` | Unsupported explicit register. Use a listed register. | [validator.py](../hasc/validator.py#L940) |
| `SetReg invalid register '{register}'. Valid registers: d0-d7, a0-a3` | Unsupported explicit register. Use a listed register and verify the ABI. | [validator.py](../hasc/validator.py#L948) |

### Interrupts

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `Interrupt '{name}': slot index {index} out of range - must be 0-15 (Amiga VBlank dispatch slots, matching AMOS-style AMAL/EVERY channels)` | Declaration uses an invalid slot. Choose 0 through 15. | [validator.py](../hasc/validator.py#L396) |
| `Interrupt '{name}': slot index {index} already used by interrupt '{other}'` | Slot is already registered. Use a distinct slot or one handler. | [validator.py](../hasc/validator.py#L402) |
| `Interrupt '{name}': name already used by another proc/func/macro` | Handler name collision. Rename it. | [validator.py](../hasc/validator.py#L408) |
| `In interrupt '{name}': interrupt procs must always return void (found 'return <expr>;')` | Interrupt returns a value. Use bare `return;`. | [validator.py](../hasc/validator.py#L683) |
| `In proc '{proc}': {keyword}({index}) - interrupt index must be 0-15` | `starti`/`endi` uses an invalid slot. Use a valid declared slot. | [validator.py](../hasc/validator.py#L786) |
| `In proc '{proc}': {keyword}({index}) refers to an interrupt slot that was never declared with 'interrupt NAME({index}) -> void { ... }'` | `starti`/`endi` names an undeclared slot. Add/correct the interrupt declaration. | [validator.py](../hasc/validator.py#L791) |

## Code Generation Errors

[_fail](../hasc/codegen.py#L61) raises `CodeGenError` with the supplied message.
The CLI adds the code-generation wrapper described above. These checks are
errors, not warnings, including errors mentioning a check the validator should
have caught. Some are reachable chiefly with `--no-validate` or a constructed AST.

### Arithmetic and CPU-Specific Checks

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `{op_name} uses 68000 word arithmetic; {side} constant {value} is outside signed 16-bit range (-32768..32767).` | Constant exceeds the signed word-lowering domain. On the 68000 path, use valid operand values or a deliberate wider-arithmetic implementation; use `--cpu 68020` only when that CPU is available. The literal-range check is not disabled by `strict16arith(off)`. | [codegen.py](../hasc/codegen.py#L91) |
| `{op_name} uses 68000 word arithmetic; {side} constant {value} is outside unsigned 16-bit range (0..65535).` | Same restriction for unsigned word lowering. Use the correct unsigned range or a wider arithmetic path. | [codegen.py](../hasc/codegen.py#L292) |
| `68000 {op_name}{where}: {side} operand '{operand}'{declared} cannot be proven to fit the {domain} 16-bit range, but the 68000 lowering ({instructions}) only uses 16-bit operands, so the value would be silently truncated. Either compile with --cpu 68020 (native 32-bit multiply/divide), narrow the operand to a 16-bit type, or change this module's '#pragma strict16arith' to (off) to accept the truncation.` | Strict word-arithmetic proof failed on the 68000 lowering path. `domain` is `signed`/`unsigned`; instructions are `MULS.W/DIVS.W` or `MULU.W/DIVU.W`; optional location is ` at line {line}`, optional type is ` (declared '{type}')`. Prove/use the correct range or select a suitable CPU; disabling the pragma deliberately accepts truncation, not full-width arithmetic. | [builder](../hasc/codegen.py#L258), [signed check](../hasc/codegen.py#L282), [unsigned check](../hasc/codegen.py#L325) |
| `Division by zero constant in expression.` | Constant-folded division has a zero divisor. Correct the expression. | [codegen.py](../hasc/codegen.py#L1637) |
| `Modulo by zero constant in expression.` | Constant-folded remainder has a zero divisor. Correct the expression. | [codegen.py](../hasc/codegen.py#L1661) |
| `Unable to allocate scratch register for 32-bit divide remainder.` | No distinct scratch register available for the long-divide remainder path (68020 instruction selection). Reduce expression pressure as a workaround and report the case. | [codegen.py](../hasc/codegen.py#L378) |

These word-arithmetic messages describe the **68000 lowering**, not a general
16-bit limit on HAS variables or on the 68020 target. CPU selection uses
[TargetSpec](../hasc/target.py); it does not make the executable safe to run on
an older physical CPU.

### Structs, Arrays and Symbols

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `Cannot resolve pointee struct type for (*{ptr_desc}).{field}; declare a typed pointer (e.g. 'T*') whose pointee is a known struct` | Struct pointer's pointee layout is unknown. Declare the actual struct pointer type and make its layout available. | [read](../hasc/codegen.py#L930), [write](../hasc/codegen.py#L3145) |
| `Unknown struct member '{struct_type}.{field}'`; `Unknown struct member '{name}.{field}'` | Layout has no requested field. Correct the field/base type. | [typed read](../hasc/codegen.py#L936), [named read](../hasc/codegen.py#L958), [typed write](../hasc/codegen.py#L3151), [named write](../hasc/codegen.py#L3165) |
| `Only 1D array indexing supported for structs; '{name}' has {count} dimensions` | Multiple indices on a struct-array read. Flatten the index/use a supported 1D layout. | [codegen.py](../hasc/codegen.py#L994) |
| `Cannot load whole struct '{struct}' through '{name}[i]'; index a field instead, e.g. '{name}[i].field'` | Whole-struct value requested through an indexed base. Read individual fields. | [first path](../hasc/codegen.py#L1030), [second path](../hasc/codegen.py#L1071) |
| `Cannot assign a whole struct '{struct}' through '{name}[i]'; assign a field instead, e.g. '{name}[i].field = ...'` | Unsupported whole-struct store. Assign fields individually. | [codegen.py](../hasc/codegen.py#L3253) |
| `Cannot determine column count for 2D array '{name}' - declare with explicit dimensions like 'int[3][5]'` | Missing column metadata for 2D access. Declare explicit dimensions. | [codegen.py](../hasc/codegen.py#L1171) |
| `Cannot determine column count for 2D array '{name}'; declare with explicit dimensions like 'int[3][5]' or use 1D arrays` | Another 2D read path lacks dimensions. Declare dimensions or flatten the array. | [codegen.py](../hasc/codegen.py#L1195) |
| `Cannot determine column count for 2D array '{name}'; declare explicit dimensions like 'int[3][5]'` | Address calculation lacks 2D dimensions. Declare them explicitly. | [codegen.py](../hasc/codegen.py#L1816) |
| `Cannot determine column count for 2D array '{name}' - must declare with explicit dimensions like 'int[3][5]'` | 2D assignment lacks column count. Declare dimensions. | [codegen.py](../hasc/codegen.py#L3279) |
| `Undefined variable '{name}' in expression` | Expression name cannot be resolved. Declare/correct it and enable validation. | [codegen.py](../hasc/codegen.py#L1358) |
| `Unresolved stack parameter '{name}' in post-increment expression`; `Undefined variable '{name}' in post-increment expression` | Unresolvable `name++`. Check declaration/signature; a declared unresolved parameter is an internal error. | [parameter](../hasc/codegen.py#L1950), [variable](../hasc/codegen.py#L1979) |
| `Unresolved stack parameter '{name}' in post-decrement expression`; `Undefined variable '{name}' in post-decrement expression` | Unresolvable `name--`. Check declaration/signature or report incorrect resolution. | [parameter](../hasc/codegen.py#L2015), [variable](../hasc/codegen.py#L2043) |
| `Unresolved stack parameter '{name}' in pre-increment expression`; `Undefined variable '{name}' in pre-increment expression` | Unresolvable `++name`. Check declaration/signature or report incorrect resolution. | [parameter](../hasc/codegen.py#L2079), [variable](../hasc/codegen.py#L2105) |
| `Unresolved stack parameter '{name}' in pre-decrement expression`; `Undefined variable '{name}' in pre-decrement expression` | Unresolvable `--name`. Check declaration/signature or report incorrect resolution. | [parameter](../hasc/codegen.py#L2141), [variable](../hasc/codegen.py#L2167) |
| `Unresolved stack parameter '{name}' in increment/decrement statement`; `Undefined variable '{name}' in increment/decrement statement` | Statement form cannot resolve its operand. Check declaration/signature or report incorrect resolution. | [parameter](../hasc/codegen.py#L3959), [variable](../hasc/codegen.py#L3967) |
| `Cannot index through 'void*': the element size is undefined. Declare the pointer with a concrete element type (e.g. 'byte*', 'int*').` | No stride for void-pointer indexing. Use the concrete pointee type. | [codegen.py](../hasc/codegen.py#L4096) |
| `String literal cannot be stored in {size}-byte field (only 1-byte .b fields are supported)` | String initializer assigned to a non-byte struct field. Use byte storage or a correctly typed scalar value. | [codegen.py](../hasc/codegen.py#L4472) |
| `Unresolved dimension name '{dimension}' in array size for '{name}' (should have been caught by validator)` | Dimension constant unresolved. Define it and leave validation enabled. | [codegen.py](../hasc/codegen.py#L4511) |
| `Cannot allocate BSS struct '{name}' with unresolved dimensions: {count}\nPlease define missing constants or use numeric dimensions.` | BSS struct count cannot be parsed. Define missing constants/use numeric dimensions. The current raise supplies `0` as a second exception argument, so Python may display an argument tuple rather than just this string. | [codegen.py](../hasc/codegen.py#L4523) |

### Control Flow, Python and Internal Resolution

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `POP() without matching PUSH() - unbalanced register save/restore` | Restore without a corresponding tracked save. Correct save/restore balance. | [codegen.py](../hasc/codegen.py#L3483) |
| `Loop variable '{name}' not found in local variables (should have been caught by validator)` | Missing loop-local metadata. Enable validation; report if valid source still fails. | [codegen.py](../hasc/codegen.py#L3662) |
| `For-loop with zero step creates infinite loop (step={step})` | Constant zero step. Use a nonzero step. | [codegen.py](../hasc/codegen.py#L3783) |
| `countdown until (...) could not lower to DBcc (expected a simple comparison; should have been caught by validator)` | Unsupported countdown comparison reaches lowering. Use a simple comparison and enable validation. | [codegen.py](../hasc/codegen.py#L3905) |
| `break statement outside of loop (should have been caught by validator)` | No enclosing loop. Move/remove the break. | [codegen.py](../hasc/codegen.py#L3917) |
| `continue statement outside of loop (should have been caught by validator)` | No enclosing loop. Move/remove the continue. | [codegen.py](../hasc/codegen.py#L3922) |
| `Undefined macro or function '{name}' (should have been caught by validator)` | No callable definition. Correct declaration/include and enable validation. | [codegen.py](../hasc/codegen.py#L3988) |
| `@python directive execution failed: {exception}` | Embedded Python raised an exception. Debug its code/imports and inspect the supplied exception. | [codegen.py](../hasc/codegen.py#L4055) |
| `Unsupported statement type: {type}` | AST statement has no lowering implementation. Reduce/report the construct. | [codegen.py](../hasc/codegen.py#L4057) |
| `Internal error: unresolved stack parameter '{name}' in address-of operator` | Declared stack parameter has no offset. Report with signature and address-of expression. | [codegen.py](../hasc/codegen.py#L1870) |
| `Internal error: unresolved variable '{name}' in address-of operator` | Address-of name has no resolvable storage. Enable validation/check the declaration; report valid cases. | [codegen.py](../hasc/codegen.py#L1890) |
| `Internal error: unresolved offset for variable '{name}' in function call argument` | Call argument storage offset missing. Report declaration and call. | [codegen.py](../hasc/codegen.py#L2348) |
| `Internal error: unresolved variable '{name}' in function call argument (not found in locals, globals, constants, or parameters)` | Call argument name unresolved. Correct declaration or report resolution failure. | [codegen.py](../hasc/codegen.py#L2424) |
| `Internal error: local variable '{name}' not found in locals_info (variable resolution failure)` | Local declaration metadata missing. Reduce/report the procedure. | [codegen.py](../hasc/codegen.py#L3021) |
| `Internal error: unresolved register for parameter in call to '{callee}' - cannot save to stack` | Register-argument save cannot resolve its register. Check ABI annotations, then report. | [codegen.py](../hasc/codegen.py#L4242) |
| `Internal error: parameter '{name}' has invalid register type: {type}` | Invalid register metadata. Check signature/annotations; report valid-source failures. | [codegen.py](../hasc/codegen.py#L4278) |
| `Internal error: unresolved register for parameter in call to '{callee}' - cannot restore from stack` | Register-argument restore cannot resolve its register. Check ABI annotations, then report. | [codegen.py](../hasc/codegen.py#L4299) |

## Allocator, Addressing Helpers and Optimizer

These helper failures can surface as uncaught Python exceptions unless the
caller translates them. They are not additional semantic warnings.

| Severity / message | Cause and practical remedy | Source |
| --- | --- | --- |
| Error: `Register allocator leak{where}: {summary}` | Allocations/spills remain at procedure exit. `where` is empty or ` ({proc})`; summary lists live data/address registers, spills and available registers. Report a reduced procedure; this is a compiler bookkeeping failure. Codegen translates it to `CodeGenError`. | [allocator](../hasc/register_allocator.py#L160), [translation](../hasc/codegen.py#L73) |
| Helper warning: `Warning: Using unallocated register {reg} in: {code_line}` | `validate_usage()` observes a data/address register not marked live. It **returns** strings; no current compiler caller emits them. For helper/API users, fix allocation tracking, not merely the generated instruction. | [data register](../hasc/register_allocator.py#L168), [address register](../hasc/register_allocator.py#L171) |
| Error: `Stride must be positive, got {stride}` | Address planner receives a nonpositive stride. Check element layout/dimensions; report a bad computed stride. | [plan](../hasc/indexed_address.py#L49), [operand](../hasc/indexed_address.py#L103) |
| Error: `Indexed displacement must fit signed 8-bit brief form` | Brief indexed operand displacement is outside -128..127. Caller must choose a different addressing plan; report invalid lowering. | [indexed_address.py](../hasc/indexed_address.py#L109) |
| Error: `struct-array read expects a single index expression` | Indexed struct helper receives multiple/no indices. Use supported 1D indexing or report the caller. | [codegen_indexed_address.py](../hasc/codegen_indexed_address.py#L223) |
| Assertion: `emit_1d_array_read expects variable index; codegen.py must filter constants` | Constant index incorrectly routed to variable-index helper. Report generated AST/source. | [codegen_indexed_address.py](../hasc/codegen_indexed_address.py#L93) |
| Assertion: `Invalid reg_left: {reg_left}`; `Invalid reg_right: {reg_right}` | Binary operation receives a missing/non-string register. Report compiler failure. | [left](../hasc/codegen.py#L866), [right](../hasc/codegen.py#L867) |
| Error: `Unsupported CPU target: {cpu}` | Programmatic `TargetSpec.for_cpu()` receives an unsupported target; CLI choices normally reject it first. Use `68000` or `68020`. | [target.py](../hasc/target.py#L47) |
| Error: `Installed HAS tool not found: {tool_path}` | Installed tool runner cannot locate a bundled script. Repair/reinstall the package and check its tool files. | [tool_runner.py](../hasc/tool_runner.py#L17) |

[peepholeopt.py](../hasc/peepholeopt.py), [reachability.py](../hasc/reachability.py),
[asm_substitution.py](../hasc/asm_substitution.py),
[codegen_utils.py](../hasc/codegen_utils.py), and [ast.py](../hasc/ast.py)
define no authored warning/error emission sites in this inventory.
[macro_expander.py](../hasc/macro_expander.py) and debug-enabled codegen can print
`DEBUG:`/allocation tracing, which is not warning/error severity. Ordinary
Python exceptions in these modules remain possible. Assertions are disabled
by Python's `-O`; disabling them is not a correctness fix.

## Asset Import Front End

Except for explicitly full messages below, errors from `asset_import.py` have
the prefix `Preprocessor error at line {line_no}:`. An unknown-option list is
sorted and comma-separated. Fix the source `#import` declaration, not the
generated assembly. Most option-validation failures are `SyntaxError`; missing
tool/dependency and converter failures may instead escape as tracebacks.

### Syntax and Options

| Message body | Cause and practical remedy | Source |
| --- | --- | --- |
| `invalid {name} value` | Boolean option is not true/false, 1/0, yes/no or on/off (case-insensitive). Use an accepted boolean spelling. | [asset_import.py](../hasc/asset_import.py#L71) |
| `{name} must be an integer` | Integer conversion failed. Use decimal, `0x` hex or `$` hex where parsed by this helper. | [asset_import.py](../hasc/asset_import.py#L88) |
| `#import requires 'as <label>' (e.g. #import bob "x.png" as my_bob;)` | Import lacks the required label clause. Add it. | [asset_import.py](../hasc/asset_import.py#L128) |
| `invalid #import syntax: {line}` | Import does not match the declaration grammar. Correct quoting/kind/label syntax. | [asset_import.py](../hasc/asset_import.py#L132) |
| `not an #import line` | Parser helper called on a different line. Correct the caller or directive. | [asset_import.py](../hasc/asset_import.py#L135) |
| `duplicate option '{key}' in #import` | Option supplied twice. Keep one value. | [asset_import.py](../hasc/asset_import.py#L147) |
| `unknown font import option(s): {options}` | Unsupported font options. Remove/correct them; font accepts no options. | [asset_import.py](../hasc/asset_import.py#L160) |
| `unknown music import option(s): {options}` | Unsupported music options. Remove/correct them; music accepts no options. | [asset_import.py](../hasc/asset_import.py#L170) |
| `unknown sound import option(s): {options}` | Unknown sound options. Use the supported sound metadata keys. | [asset_import.py](../hasc/asset_import.py#L182) |
| `unknown bob import option(s): {options}` | Unknown BOB options. Use supported keys/spelling. | [asset_import.py](../hasc/asset_import.py#L207) |
| `bob planes must be 1..5` | Invalid/noninteger plane count. Use 1 through 5. | [conversion](../hasc/asset_import.py#L220), [range](../hasc/asset_import.py#L224) |
| `bob dither must be none\|fs (got {value!r})` | Unsupported BOB dither. Use `none` or `fs`. | [asset_import.py](../hasc/asset_import.py#L231) |
| `unknown sprite import option(s): {options}` | Unknown sprite options. Correct the option names. | [asset_import.py](../hasc/asset_import.py#L247) |
| `hardware sprites are fixed at {planes} bitplanes ({colors} colours); got planes={value}` | Sprite plane count is not 2. Use 2 planes, 4 colors. | [asset_import.py](../hasc/asset_import.py#L261) |
| `hardware sprites are fixed at {colors} colours (2 bitplanes); got colors={value}` | Sprite color count is not 4. Use 4 colors. | [asset_import.py](../hasc/asset_import.py#L269) |
| `sprite dither must be none\|fs (got {value!r})` | Unsupported sprite dither. Use `none` or `fs`. | [asset_import.py](../hasc/asset_import.py#L277) |
| `unknown palette import option(s): {options}` | Unknown palette options. Correct the option names. | [asset_import.py](../hasc/asset_import.py#L293) |
| `palette import: use only one of colors= or planes=` | Both size options supplied. Choose one. | [asset_import.py](../hasc/asset_import.py#L298) |
| `palette planes must be 1..5` | Invalid/noninteger plane count. Use 1 through 5. | [conversion](../hasc/asset_import.py#L312), [range](../hasc/asset_import.py#L316) |
| `palette colors must be 2..32` | Invalid/noninteger color count. Use 2 through 32. | [conversion](../hasc/asset_import.py#L324), [range](../hasc/asset_import.py#L328) |
| `palette dither must be none\|fs\|ordered (got {value!r})` | Unsupported palette dither. Use a listed mode. | [asset_import.py](../hasc/asset_import.py#L335) |
| `index0 must be backdrop\|transparent\|none` | Invalid palette index-zero policy. Choose the policy that matches the asset. | [asset_import.py](../hasc/asset_import.py#L343) |
| `unknown image import option(s): {options}` | Unknown picture options. Correct the option names. | [asset_import.py](../hasc/asset_import.py#L371) |
| `image mode must be lores\|hires\|ham6 (aliases: 320x256x32, 640x256x16, mode0\|mode1\|mode2); got {value!r}` | Unsupported display mode. Choose a listed mode/alias. | [asset_import.py](../hasc/asset_import.py#L384) |
| `image dither must be none\|fs\|ordered (got {value!r})` | Unsupported picture dither. Use a listed mode. | [asset_import.py](../hasc/asset_import.py#L393) |
| `unknown atlas import option(s): {options}` | Unknown atlas options. Correct the option names. | [asset_import.py](../hasc/asset_import.py#L409) |
| `#import atlas v1 supports kind=bob only (got kind={kind!r}); hardware sprites need 16px-wide single frames via #import sprite` | Atlas kind is unsupported. Use `kind=bob` or import individual hardware sprite frames. | [asset_import.py](../hasc/asset_import.py#L427) |
| `atlas planes must be 1..5` | Atlas plane count outside range. Use 1 through 5. | [asset_import.py](../hasc/asset_import.py#L436) |
| `atlas dither must be none\|fs (got {value!r})` | Unsupported atlas dither. Use `none` or `fs`. | [asset_import.py](../hasc/asset_import.py#L443) |
| `atlas sprites= list is empty` | Frame filter has no names. Supply a nonempty list or omit it. | [asset_import.py](../hasc/asset_import.py#L464) |
| `unknown tileset import option(s): {options}` | Unknown tileset options. Correct the option names. | [asset_import.py](../hasc/asset_import.py#L480) |
| `tileset tile_w must be 8, 16, or 32`; `tileset tile_h must be 8, 16, or 32` | Unsupported tile size. Use a listed width/height. | [width](../hasc/asset_import.py#L499), [height](../hasc/asset_import.py#L503) |
| `tileset planes must be 1..5` | Invalid plane count. Use 1 through 5. | [asset_import.py](../hasc/asset_import.py#L509) |
| `tileset dither must be none\|fs (got {value!r})` | Unsupported tileset dither. Use `none` or `fs`. | [asset_import.py](../hasc/asset_import.py#L516) |
| `tileset strict_palette requires match_palette=<label>` | Strict matching requested without a palette. Supply the defining import label. | [asset_import.py](../hasc/asset_import.py#L528) |
| `unknown tilemap import option(s): {options}` | Unknown tilemap options. Correct the option names. | [asset_import.py](../hasc/asset_import.py#L539) |
| `tilemap layer= and layers= are mutually exclusive` | Single-layer and multi-layer selectors both used. Choose one. | [asset_import.py](../hasc/asset_import.py#L556) |
| `tilemap index_size must be b\|w (got {size!r})` | Unsupported index width. Use byte (`b`) or word (`w`). | [asset_import.py](../hasc/asset_import.py#L565) |

In table message cells, `\|` represents a literal `|` in the emitted message.

### Files, Conversion Wrappers and Dependencies

| Message body (or explicitly full message) | Cause and practical remedy | Source |
| --- | --- | --- |
| `hardware sprite PNG must be exactly {width} pixels wide (got {w}x{h} from {file}); resize or crop the source` followed by `#import will not stretch it` | PNG width is not 16 pixels. Resize/crop the source to 16; the actual text joins the two clauses with a Unicode em dash. | [asset_import.py](../hasc/asset_import.py#L640) |
| `{exception}` | Font converter `ValueError` wrapped with a preprocessor line. Correct the font bytes/source using the helper messages below. | [asset_import.py](../hasc/asset_import.py#L703) |
| `#import sound 8SVX extract failed: {exception}` | Sample extractor failed. Use valid uncompressed 8SVX/PCM and check the nested error. | [asset_import.py](../hasc/asset_import.py#L756) |
| `#import sound expects .raw, .iff, or .8svx (got {file})` | Unsupported sound suffix reaches generator. Use an accepted sample format. | [asset_import.py](../hasc/asset_import.py#L761) |
| `#import atlas atlas_png not found: {path}` | Explicit image override missing. Correct `atlas_png`. | [asset_import.py](../hasc/asset_import.py#L879) |
| `#import atlas PNG not found: {path} (from XML imagePath={image_path!r}; use atlas_png=...)` | XML's image path cannot be resolved. Supply the actual image or override its path. | [asset_import.py](../hasc/asset_import.py#L889) |
| `match_palette= is empty` | Empty matching label. Supply the palette label. | [asset_import.py](../hasc/asset_import.py#L1007) |
| `match_palette={label!r} not found under {outdir} (import the atlas/bob/palette that defines it first)` | Palette assembly cannot be found in generated assets. Import its provider first and check label/output directory. | [asset_import.py](../hasc/asset_import.py#L1018) |
| `#import tileset: {exception}` | Tileset helper `ValueError`. Fix image dimensions/palette according to the nested message. | [asset_import.py](../hasc/asset_import.py#L1057) |
| `#import tilemap: {exception}` | Map helper `ValueError`. Fix map encoding/layers/tileset references. | [asset_import.py](../hasc/asset_import.py#L1086) |
| `unknown #import kind '{kind}' (expected bob\|palette\|sprite\|atlas\|tileset\|tilemap\|font\|music\|sound\|image)` | Unknown import kind. Use a supported kind. | [asset_import.py](../hasc/asset_import.py#L1136) |
| `#import file not found: {path}` | Missing source asset. Correct the source-relative path. | [asset_import.py](../hasc/asset_import.py#L1148) |
| `#import atlas expects a TexturePacker .xml file (got {file})` | Wrong atlas suffix/format. Export TexturePacker XML. | [asset_import.py](../hasc/asset_import.py#L1160) |
| `#import tilemap expects a Tiled .tmx or .json file (got {file})` | Wrong map suffix/format. Export a supported Tiled map. | [asset_import.py](../hasc/asset_import.py#L1172) |
| `#import font expects a C64 charset .bin, .s, or .asm file (got {file})` | Unsupported charset source. Convert to a supported C64 source format. | [asset_import.py](../hasc/asset_import.py#L1181) |
| `#import music expects a ProTracker .mod file (got {file})` | Wrong music suffix. Supply a ProTracker MOD. | [asset_import.py](../hasc/asset_import.py#L1190) |
| `#import sound expects a .raw, .iff, or .8svx file (got {file})` | Wrong sample suffix. Supply a supported sample file. | [asset_import.py](../hasc/asset_import.py#L1202) |
| `#import image expects PNG/JPEG/GIF/BMP/IFF (got {file})` | Unsupported picture suffix. Supply a supported image format. | [asset_import.py](../hasc/asset_import.py#L1213) |
| `unhandled #import kind {kind!r}` | Recognized import reached no generation branch. Report compiler dispatch failure. | [asset_import.py](../hasc/asset_import.py#L1295) |
| Full: `Asset tool not found: {path}` | Bundled tool script missing. Repair the installation. | [asset_import.py](../hasc/asset_import.py#L101) |
| Full: `Cannot load asset tool: {path}` | Python cannot create a module spec/loader. Check the installation and file type. | [asset_import.py](../hasc/asset_import.py#L110) |
| Full: `Pillow is required for #import (pip install pillow)` | Pillow import failed. Install Pillow into the compiler's interpreter; inspect a chained exception if already installed. | [asset_import.py](../hasc/asset_import.py#L691) |
| Full: `#import atlas produced no BOBs from {xml_file}` | Atlas conversion returned no BOB entries. Check selected frames and earlier converter errors. | [asset_import.py](../hasc/asset_import.py#L937) |
| Full: `iter_audio_imports kind must be music\|sound, got {kind!r}` | Helper API given a non-audio kind. Fix the programmatic caller. | [asset_import.py](../hasc/asset_import.py#L1335) |
| Assertion with no authored message | Atlas generation reached a state without a resolved PNG path. Report the source declaration and XML. | [asset_import.py](../hasc/asset_import.py#L1263) |

## Assembler, Linker and ADF Errors

These are HAS-authored `ToolchainError` messages used by `--exe`/`--adf`, not
parser/validator failures. vasm/vlink/xdftool output nested inside them belongs
to the external tool and varies by version and input.

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `VASM is set to {value!r} but that assembler was not found.` | Bad assembler override. Set `VASM` to an existing executable. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L112) |
| `Assembler not found (tried: vasmm68k_mot, vasm68000_mot). Install vasm or set VASM=/path/to/vasmm68k_mot.` | No assembler found. Install vasm/add PATH or set `VASM`. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L121) |
| `VLINK is set to {value!r} but that linker was not found.` | Bad linker override. Set `VLINK` correctly. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L134) |
| `Linker not found (tried: vlink). Install vlink or set VLINK=/path/to/vlink.` | No linker found. Install/add PATH or set `VLINK`. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L142) |
| `Unsupported CPU for vasm: {cpu}` | Toolchain API receives an unsupported CPU. Use 68000/68020. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L156) |
| `{label} executable not found: {command_0}` | Tool disappeared/cannot launch. Check command path/PATH/interpreter. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L269) |
| `{label} failed (exit {returncode}):` followed by `  command: {command}`, optionally `  stdout:\n{stdout}` and `  stderr:\n{stderr}` | External tool returned nonzero. Read its output: fix assembly, unresolved symbols, command paths or ADF inputs as appropriate. | [builder and raise](../hasc/amiga_toolchain.py#L272), [raise](../hasc/amiga_toolchain.py#L278) |
| `vlink produced no executable at {exe_path}` | Link command returned but output is absent/empty. Inspect destination, linker and its output. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L322) |
| `{exception}\nNote: no lib/ xdef provider found for: {symbols}. Add the providing .s under lib/ or link extra objects manually.` | Failed link plus externs with no discovered library provider. Supply the implementation object/library; a declaration alone is insufficient. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L387) |
| `Python interpreter for amitools not found: {python}` | amitools probe interpreter missing. Correct the helper's interpreter argument. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L423) |
| `xdftool / amitools not found. Install amitools in the project venv ('.venv/bin/python3 -m pip install amitools') or set XDFTOOL=/path/to/xdftool.` | No xdftool and module probe failed. Install amitools in the active interpreter or set `XDFTOOL`; the embedded command uses POSIX syntax, so on Windows use the actual venv Python path. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L430) |
| `Executable not found for ADF: {exe_path}` | ADF helper cannot find the executable. Build it/correct its path first. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L447) |
| `ADF was not created at {adf_path}` | xdftool returned but image is absent/empty. Inspect tool version, command and destination. | [amiga_toolchain.py](../hasc/amiga_toolchain.py#L499) |

## Repository Asset-Helper Diagnostics

`#import` invokes the Python APIs in the following repository tools. These are
**HAS repository-authored** messages, not third-party exceptions. They may be
wrapped by the asset front end as described above, or propagate with their
Python exception class/traceback. Some helper guards duplicate earlier front-end
checks, so normally the front-end wording is seen first. Standalone tool CLI
usage errors are not compiler diagnostics; CLI-only cases are identified below
to avoid confusing them with `#import` output.

### Dependency and Missing-File Guards

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `Pillow is required for bob importing (pip install pillow)` | Pillow unavailable in BOB conversion. Install it in the active interpreter. | [quantizer](../tools/bob_importer.py#L67), [converter](../tools/bob_importer.py#L181), [standalone path](../tools/bob_importer.py#L475) |
| `Pillow is required for sprite importing (pip install pillow)` | Pillow unavailable in sprite conversion. Install it in the active interpreter. | [converter](../tools/sprite_importer.py#L68), [standalone path](../tools/sprite_importer.py#L214) |
| `Pillow is required (pip install pillow)` | Pillow unavailable in shared palette/atlas conversion. Install it in the active interpreter. | [atlas palette](../tools/texturepacker_atlas_importer.py#L63), [atlas processor](../tools/texturepacker_atlas_importer.py#L517), [palette helpers](../tools/amiga_palette.py#L180), [ordered dither](../tools/amiga_palette.py#L255), [palette converter](../tools/amiga_palette.py#L449) |
| `Pillow is required for tile importing (pip install pillow)` | Pillow unavailable for tiles. Install it in the active interpreter. | [converter](../tools/tile_importer.py#L227), [standalone path](../tools/tile_importer.py#L420) |
| `Pillow is required for image import (pip install pillow)` | Pillow unavailable for pictures. Install it in the active interpreter. | [image_importer.py](../tools/image_importer.py#L65) |
| `FileNotFoundError` carrying the requested path (no additional authored prose) | File disappeared, path is wrong, or an API/standalone caller bypassed the front-end existence check. Correct the path/check that assets remain available. | [BOB](../tools/bob_importer.py#L473), [sprite](../tools/sprite_importer.py#L212), [palette assembly](../tools/amiga_palette.py#L101), [tileset palette](../tools/tile_importer.py#L59), [tileset standalone](../tools/tile_importer.py#L418), [map](../tools/tiled_map_importer.py#L198), [IFF standalone](../tools/iff_importer.py#L632), [picture standalone](../tools/image_importer.py#L335) |

### TexturePacker Atlas

| Severity / message | Cause and practical remedy | Source |
| --- | --- | --- |
| Warning: `  [WARN] Skipping zero-size sprite: {name}` | XML frame has nonpositive width/height. Correct/remove that frame in the atlas export. Conversion skips it. | [texturepacker_atlas_importer.py](../tools/texturepacker_atlas_importer.py#L107) |
| Error: `XML not found: {xml_path}` | Missing XML file. Correct the path. | [texturepacker_atlas_importer.py](../tools/texturepacker_atlas_importer.py#L521) |
| Error: `Atlas PNG not found: {atlas_png_path}\n  Hint: use --atlas-png <path> to override the location.` | Missing atlas image. Restore the image or use `atlas_png=` in `#import`; `--atlas-png` is the standalone tool option. | [texturepacker_atlas_importer.py](../tools/texturepacker_atlas_importer.py#L540) |
| Error output: `  [ERROR] {name}: {exception}` | Individual sprite extraction failed. Inspect/fix frame coordinates/data and nested exception. The processor catches it and continues with other frames; output can therefore be partial. | [texturepacker_atlas_importer.py](../tools/texturepacker_atlas_importer.py#L577) |
| Status: `No sprites to process.` | No frames remain after parsing/filtering. Check `sprites=` and frame sizes. The helper returns no results; the HAS caller can then raise `#import atlas produced no BOBs ...`. | [texturepacker_atlas_importer.py](../tools/texturepacker_atlas_importer.py#L561) |
| Internally caught: `regenerate deduplicated output in default mode` | Cached output has alias/external-palette layout inconsistent with the requested mode. An `OSError` intentionally forces regeneration and is caught locally; it is **not emitted** as a compiler error. No source fix is required. | [raise](../tools/texturepacker_atlas_importer.py#L650), [catch](../tools/texturepacker_atlas_importer.py#L679) |

### Palette Matching and Tilesets

All messages in this subsection are errors. Shared palette parsing has slightly
different wording from the older tileset parser; both spellings are retained.

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `Palette label '{wanted}' not found in {asm_path}` | Named palette label absent. Use the actual exported label/import its provider. | [shared](../tools/amiga_palette.py#L109), [tileset](../tools/tile_importer.py#L68) |
| `No palette label found in {asm_path}`; `No *_palette label found in {asm_path}` | No discoverable palette label. Supply generated palette assembly or specify the correct label. | [shared](../tools/amiga_palette.py#L116), [tileset](../tools/tile_importer.py#L72) |
| `Palette label found in {asm_path}, but no DC.W palette values followed` | Label exists without parseable palette words. Supply valid generated RGB4 `DC.W` palette data. | [shared](../tools/amiga_palette.py#L129), [tileset](../tools/tile_importer.py#L91) |
| `No palette DC.W values found in {asm_path}` | Assembly contains no parseable palette values. Use the palette output, not unrelated assembly. | [shared](../tools/amiga_palette.py#L132), [tileset](../tools/tile_importer.py#L94) |
| `Destination palette is empty` | Palette remapping has no target colors. Supply a nonempty palette. | [tile_importer.py](../tools/tile_importer.py#L122) |
| `Strict palette match failed: source colors used by tiles are missing in target palette: {missing_desc}` | Used source colors are absent from target palette. Re-export against the same palette, add required colors, or deliberately permit non-strict remapping. | [tile_importer.py](../tools/tile_importer.py#L169) |
| `tile_width must be 8, 16, or 32, got {width}`; `tile_height must be 8, 16, or 32, got {height}` | Unsupported tile dimensions. Use the listed sizes (`tile_w`/`tile_h` in `#import`). | [width](../tools/tile_importer.py#L230), [height](../tools/tile_importer.py#L232) |
| `--strict-palette-match requires --match-bob-palette` | Helper called with strict matching but no target palette. In HAS use `strict_palette` together with `match_palette=<label>`; the message names standalone flags. | [tile_importer.py](../tools/tile_importer.py#L235) |
| `Image width {width} must be multiple of tile_width {tile_width}`; `Image height {height} must be multiple of tile_height {tile_height}` | Image cannot be divided into complete tiles. Resize/pad/crop to exact tile multiples. | [width](../tools/tile_importer.py#L297), [height](../tools/tile_importer.py#L300) |
| `colors must be between 2 and 32, got {colors}` | Palette size outside supported range, including the post-normalization check. Use 2 through 32. | [first check](../tools/amiga_palette.py#L452), [second check](../tools/amiga_palette.py#L455) |
| `index0 must be 'backdrop', 'transparent', or 'none'` | Invalid index-zero policy in shared converter. Use a listed policy. | [amiga_palette.py](../tools/amiga_palette.py#L459) |
| `dither must be 'none', 'fs', or 'ordered'` | Invalid shared converter dither. Use a listed mode. | [amiga_palette.py](../tools/amiga_palette.py#L462) |
| `planes must be 1..5, got {planes}` | Invalid bitplane count in palette helper. Use 1 through 5. | [amiga_palette.py](../tools/amiga_palette.py#L595) |

### Tiled Maps

All are errors, usually wrapped as `#import tilemap: {exception}`.

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `Unsupported layer encoding: {encoding!r}` | Base64 data uses unsupported compression/encoding. Re-export supported CSV/base64 data (base64 may use zlib/gzip). | [tiled_map_importer.py](../tools/tiled_map_importer.py#L67) |
| `Layer data size mismatch: got {bytes} bytes, expected {expected_bytes}` | Decoded binary payload is not four bytes per tile. Re-export intact map data with consistent dimensions. | [tiled_map_importer.py](../tools/tiled_map_importer.py#L70) |
| `Tile GID 0x{gid:08X} has flip flags; re-export without flipped tiles or pass allow_flip` | Flipped tile not permitted. Remove flips or explicitly use `allow_flip`; it strips flags, it does not render the flip. | [first path](../tools/tiled_map_importer.py#L87), [layer path](../tools/tiled_map_importer.py#L290) |
| `Map has no tile layers` | Map contains no supported tile layers. Export at least one tile layer. | [single selection](../tools/tiled_map_importer.py#L206), [multi selection](../tools/tiled_map_importer.py#L221) |
| `Layer {name!r} not found (available: {names})` | Requested layer is absent. Use an available name; check single/multi-layer selection. | [single](../tools/tiled_map_importer.py#L212), [multi](../tools/tiled_map_importer.py#L236) |
| `layers= requires 'all' or a comma-separated name list` | Empty/invalid multi-layer selector. Supply `all` or names. | [tiled_map_importer.py](../tools/tiled_map_importer.py#L230) |
| `Layer '{name}' has {count} tiles, expected {expected} ({width}x{height})` | Layer data length disagrees with dimensions. Re-export/correct the layer payload. | [tiled_map_importer.py](../tools/tiled_map_importer.py#L252) |
| `GID {gid} does not fall in any tileset range` | Tile references an unavailable tileset. Repair tileset references/first GIDs. | [tiled_map_importer.py](../tools/tiled_map_importer.py#L316) |
| `Layer mixes tiles from multiple tilesets (firstgids={firstgids}); split into separate layers or use one tileset per layer` | One layer references multiple tilesets. Split the layer or consolidate its tileset. | [tiled_map_importer.py](../tools/tiled_map_importer.py#L323) |
| `firstgid override {override} does not match layer tileset firstgid {resolved}` | Override disagrees with actual tileset. Correct/remove `firstgid`. | [tiled_map_importer.py](../tools/tiled_map_importer.py#L329) |
| `Layer {name!r} size {layer_width}x{layer_height} does not match map {width}x{height}` | Layer dimensions differ from map. Export consistent finite layers. | [tiled_map_importer.py](../tools/tiled_map_importer.py#L457) |
| `Only orthogonal maps are supported (got {orientation!r})` | Isometric/other map orientation. Export orthogonal maps. | [tiled_map_importer.py](../tools/tiled_map_importer.py#L517) |
| `index_size must be 'b' or 'w'` | Unsupported helper index size. Choose byte/word. | [tiled_map_importer.py](../tools/tiled_map_importer.py#L522) |
| `Specify either layer= or layers=, not both` | Conflicting helper selection arguments. Choose one selector. | [tiled_map_importer.py](../tools/tiled_map_importer.py#L525) |

### C64 Fonts and 8SVX Samples

All are errors. Font `ValueError` messages receive the generic preprocessor line
wrapper. Sample `EightSvxError` messages receive `#import sound 8SVX extract failed:`.

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `C64 font binary is empty: {path}` | Empty charset. Supply character bytes. | [c64_font_converter.py](../tools/c64_font_converter.py#L130) |
| `C64 font binary length must be a multiple of 8 (got {bytes} bytes from {file})` | Incomplete 8-byte glyph data. Export a complete charset. | [c64_font_converter.py](../tools/c64_font_converter.py#L132) |
| `unsupported C64 font source '{file}' (expected .bin, .s, or .asm)` | Unsupported font suffix. Use a supported source. | [c64_font_converter.py](../tools/c64_font_converter.py#L150) |
| `Unexpected EOF reading chunk header` | Truncated sample chunk header. Re-export an intact IFF. | [extract_8svx.py](../tools/extract_8svx.py#L28) |
| `File too short for IFF FORM header` | Missing complete FORM header. Use a valid 8SVX file. | [extract_8svx.py](../tools/extract_8svx.py#L37) |
| `Not an IFF file (expected FORM, got {header!r})` | Input is not IFF. Convert to 8SVX or use raw PCM. | [extract_8svx.py](../tools/extract_8svx.py#L39) |
| `Not an 8SVX FORM (got {form_type!r})` | IFF contains another FORM type. Export 8SVX, not image IFF. | [extract_8svx.py](../tools/extract_8svx.py#L42) |
| `Chunk {chunk_id!r} extends past end of file` | Invalid chunk length/truncation. Re-export the sample. | [extract_8svx.py](../tools/extract_8svx.py#L57) |
| `VHDR chunk too short` | Invalid sample header. Re-export valid 8SVX. | [extract_8svx.py](../tools/extract_8svx.py#L64) |
| `Missing BODY chunk` | No sample data. Supply a complete 8SVX. | [extract_8svx.py](../tools/extract_8svx.py#L74) |
| `Compressed 8SVX BODY not supported (sCompression={compression}); only uncompressed PCM is handled` | Compressed sample. Export uncompressed PCM 8SVX or raw PCM. | [extract_8svx.py](../tools/extract_8svx.py#L76) |
| `Source not found: {path}` | Sample source absent. Correct its path. | [extract_8svx.py](../tools/extract_8svx.py#L95) |

### Full-Screen Pictures and IFF Decoding

All are errors. Picture/helper exceptions are not uniformly translated into
preprocessor `SyntaxError`; a traceback can expose these authored messages.

| Message | Cause and practical remedy | Source |
| --- | --- | --- |
| `image mode must be lores\|hires\|ham6 (aliases: 320x256x32, 640x256x16, mode0\|mode1\|mode2); got {mode!r}` | Unsupported helper picture mode. Use a supported mode/alias. | [image_importer.py](../tools/image_importer.py#L56) |
| `dither must be none\|fs\|ordered (got {dither!r})` | Unsupported picture dither. Use a listed mode. | [image_importer.py](../tools/image_importer.py#L197) |
| `unsupported image type {file} (expected PNG/JPEG/GIF/BMP/IFF)` | Unsupported picture source type. Convert to a supported format. | [image_importer.py](../tools/image_importer.py#L202) |
| `HAM6 planar size mismatch: got {actual}, expected {expected}` | Converted HAM6 byte count violates layout. Report source, mode and converter failure. | [image_importer.py](../tools/image_importer.py#L260) |
| `{mode} bitmap size mismatch: got {actual}, expected {expected}` | Converted bitmap byte count violates mode layout. Report source, mode and converter failure. | [image_importer.py](../tools/image_importer.py#L300) |
| `Unexpected EOF reading chunk size` | Truncated IFF chunk header. Re-export an intact image. | [iff_importer.py](../tools/iff_importer.py#L58) |
| `ByteRun1: insufficient data for literal run`; `ByteRun1: insufficient data for repeat run` | Compressed payload is incomplete. Re-export intact/uncompressed ILBM. | [literal](../tools/iff_importer.py#L82), [repeat](../tools/iff_importer.py#L88) |
| `HAM decode requested for a non-HAM image` | HAM decode used on ordinary image data. Choose the correct decode mode/source. | [iff_importer.py](../tools/iff_importer.py#L182) |
| `Not an IFF file (expected FORM, got {form_id})` | Image lacks FORM header. Supply an IFF ILBM file. | [iff_importer.py](../tools/iff_importer.py#L329) |
| `Not an ILBM file (expected ILBM, got {format_type})` | IFF is not ILBM. Convert to ILBM or another supported image format. | [iff_importer.py](../tools/iff_importer.py#L336) |
| `Unexpected EOF in chunk {chunk_id}` | Image chunk truncated. Re-export the source. | [iff_importer.py](../tools/iff_importer.py#L352) |
| `BMHD chunk too small: {chunk_size}` | Invalid bitmap header. Supply valid ILBM. | [iff_importer.py](../tools/iff_importer.py#L361) |
| `Missing BMHD chunk`; `Missing BODY chunk` | Required bitmap header/data missing. Re-export a complete ILBM. | [header](../tools/iff_importer.py#L409), [data](../tools/iff_importer.py#L412) |
| `Unsupported compression type: {compression}` | Unknown ILBM compression. Export uncompressed or supported ByteRun1 data. | [iff_importer.py](../tools/iff_importer.py#L424) |

### Tool CLI Boundaries

When run independently, the atlas CLI can report
`--shared-palette requires --shared-palette-file` through argparse
([source](../tools/texturepacker_atlas_importer.py#L778)); its catch-all display
is `Error: {exception}` ([source](../tools/texturepacker_atlas_importer.py#L799)).
The standalone IFF tool similarly prints `Error: {exception}`
([source](../tools/iff_importer.py#L730)). These wrappers are not used by HAS's
direct `#import` API calls. The standalone font CLI reports
`Failed to convert font: {exception}`
([source](../tools/c64_font_converter.py#L239)) or
`Failed to write output: {exception}`
([source](../tools/c64_font_converter.py#L248)); fix the source conversion or
destination permissions respectively. The standalone sample CLI reports
`extract_8svx: {exception}`
([source](../tools/extract_8svx.py#L123)); follow the sample error above.
Standalone `SystemExit(main())` in
[image_importer.py](../tools/image_importer.py#L402) and
[tiled_map_importer.py](../tools/tiled_map_importer.py#L597) supplies exit status,
not an additional diagnostic message. Other standalone asset tools, editor
extension diagnostics, runtime library/emulator failures, and arbitrary user
generator/Python output are outside this compiler catalog.

## Scope and Maintenance

The inventory covers every Python module in `hasc/` and the ten asset-helper
modules directly/transitively loaded by `#import`: `bob_importer`,
`sprite_importer`, `texturepacker_atlas_importer`, `tile_importer`,
`tiled_map_importer`, `c64_font_converter`, `extract_8svx`, `image_importer`,
`amiga_palette`, and `iff_importer`. It includes authored raises, assertions,
failure-helper calls, error/warning collection, parser hint builders, and
diagnostic output. Repeated sites share rows; user-authored `#warning`/`#error`
contents and arbitrary nested exceptions cannot be enumerated as fixed messages.

To update the reference, inspect those emission paths as well as messages built
indirectly (for example `error_msg`, syntax hints and tool failure `parts`).
Check both CPU paths before changing target-specific claims. Check that each
authored emission site retains a source link and that all linked files/line
anchors exist. Source-line coverage is a maintenance aid, not proof that all
runtime exception texts have been enumerated or that every internal failure is
reachable from valid HAS source.