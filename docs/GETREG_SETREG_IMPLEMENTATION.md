# `GetReg` and `SetReg` Reference

`GetReg` and `SetReg` are compiler intrinsics for explicit longword register
access. They do not call a runtime library.

```has
var current: long = GetReg("d0");
SetReg("a0", address);
var written: long = SetReg("d3", current + 1);
```

The currently accepted register names are `d0`–`d7` and `a0`–`a3`.
`GetReg` evaluates to the selected register's value. `SetReg` evaluates its
value expression, writes that value to the selected register, and itself
evaluates to the value written. Both use `move.l` operations and are supported
under `--cpu 68000` and `--cpu 68020`.

These intrinsics do not preserve values across calls or override the calling
convention. Use them only when the register's liveness and the called
routine's register contract are understood.

For code-generation and allocator details, see
[Register intrinsics in the compiler developer guide](COMPILER_DEVELOPERS_GUIDE.md#register-intrinsics).
For language examples, see
[Direct Register Access in the HAS Developer's Guide](DEVELOPERS_GUIDE.md#direct-register-access).
