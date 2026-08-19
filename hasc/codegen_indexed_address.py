"""Indexed address generation helpers for Phase 2+ path conversions.

This module provides high-level wrappers around _lower_indexed_address() for each
codegen access pattern. Keeps codegen.py lean while centralizing address lowering.

Phases 2+:
- Phase 2: All paths emit 68000-style output (shifts in prelude, unscaled operands)
- Phase 3: Displacement folding for struct fields
- Phase 4: 68020 scaled operands for both 68000 and 68020 targets
"""


def emit_1d_array_read(codegen, name, index_expr, params, locals_info,
                       reg_left, reg_right, frame_reg, elem_bytes):
    """Emit code for global 1D array read with centralized address lowering.

    Args:
        codegen: CodeGen instance (provides _lower_indexed_address, _emit_expr, etc.)
        name: Array variable name
        index_expr: AST expression for array index (must be variable, not constant)
        params: Procedure parameters
        locals_info: Local variable info
        reg_left: Target register for result (e.g., 'd0')
        reg_right: Temporary register for index (e.g., 'd1')
        frame_reg: Frame pointer register ('a6' or 'a4')
        elem_bytes: Element size in bytes (stride: 1, 2, 4, or higher)

    Returns:
        List of assembly instruction strings.

    Contract:
        - Caller must ensure index_expr is NOT a compile-time constant.
        - Generated code assumes a0 is free for address calculations.
        - Emits 68000-style output for Phase 2/3 (shifts in prelude).
        - Phase 4+: helper will emit 68020 scaled operands when enabled.

    Replaces inline scaling logic with centralized _lower_indexed_address() call.
    Phase 2 contract: output is byte-for-byte identical to original inline implementation.
    """
    code = []
    from . import ast

    # Caller must filter constants; this function handles variable indices only
    assert not isinstance(index_expr, ast.Number), (
        "emit_1d_array_read expects variable index; codegen.py must filter constants"
    )

    # Evaluate index expression into reg_right (typically d1)
    index_code = codegen._emit_expr(index_expr, params, locals_info,
                                    reg_right, "d2", target_type="int", frame_reg=frame_reg)
    from .indexed_address import index_may_clobber_address_register
    if index_may_clobber_address_register(index_expr):
        code.extend(index_code)
        code.append(f"    lea {name},a0")
    else:
        code.append(f"    lea {name},a0")
        code.extend(index_code)

    # Get prelude and operand from centralized address-lowering helper
    # elem_bytes is the stride (element size in bytes)
    prelude, operand = codegen._lower_indexed_address(
        "a0", reg_right, elem_bytes, use_scaled=True
    )
    code.extend(prelude)

    # Load element with correct size suffix
    size_suffix = ast.size_suffix(elem_bytes)
    code.append(f"    move{size_suffix} {operand},{reg_left}")

    return code


def emit_typed_pointer_read(codegen, name, index_expr, params, locals_info,
                            reg_left, reg_right, frame_reg, elem_bytes, elem_type):
    """Emit code for typed pointer dereference with centralized address lowering.

    Args:
        codegen: CodeGen instance
        name: Pointer variable name or offset (e.g., 'ptr' or '-4(a6)')
        index_expr: AST expression for pointer index
        params: Procedure parameters
        locals_info: Local variable info
        reg_left: Target register for result
        reg_right: Temporary register for index
        frame_reg: Frame pointer register
        elem_bytes: Element size (1, 2, 4)
        elem_type: Element type string (e.g., 'byte', 'word', 'int')

    Returns:
        List of assembly instruction strings.
    """
    code = []

    from . import ast

    if isinstance(index_expr, ast.Number):
        code.append(f"    move.l {name},a0")
        # Constant index
        index_val = index_expr.value
        offset = index_val * elem_bytes
        size_suffix = ast.size_suffix(elem_bytes)

        if offset == 0:
            code.append(f"    move{size_suffix} (a0),{reg_left}")
        else:
            code.append(f"    move{size_suffix} {offset}(a0),{reg_left}")
    else:
        # Variable index: use centralized address lowering
        # Evaluate index into reg_right (d1)
        index_code = codegen._emit_expr(index_expr, params, locals_info,
                                        reg_right, "d2", target_type="int", frame_reg=frame_reg)
        from .indexed_address import index_may_clobber_address_register
        if index_may_clobber_address_register(index_expr):
            code.extend(index_code)
            code.append(f"    move.l {name},a0")
        else:
            code.append(f"    move.l {name},a0")
            code.extend(index_code)

        # Get prelude and operand from centralized helper
        prelude, operand = codegen._lower_indexed_address(
            "a0", reg_right, elem_bytes, use_scaled=True
        )
        code.extend(prelude)

        # Load element with correct size
        size_suffix = ast.size_suffix(elem_bytes)
        code.append(f"    move{size_suffix} {operand},{reg_left}")

    return code


def emit_untyped_global_pointer_read(codegen, name, index_expr, params,
                                    locals_info, reg_left, frame_reg):
    """Emit a byte read through a global pointer-valued symbol."""
    code = []
    index_code = codegen._emit_expr(
        index_expr,
        params,
        locals_info,
        "d1",
        "d2",
        target_type="int",
        frame_reg=frame_reg,
    )
    from .indexed_address import index_may_clobber_address_register
    if index_may_clobber_address_register(index_expr):
        code.extend(index_code)
        code.append(f"    move.l {name},a0")
    else:
        code.append(f"    move.l {name},a0")
        code.extend(index_code)
    code.append(f"    move.b (a0,d1.l),{reg_left}")
    code.append(f"    andi.l #$FF,{reg_left}")
    return code


def emit_struct_array_read(codegen, name, index_expr, params, locals_info,
                           reg_left, frame_reg, stride, field_offset,
                           field_suffix):
    """Emit a 1D struct-array member read after centralized stride lowering."""
    code = []
    if len(getattr(index_expr, "indices", [])) != 0:
        raise ValueError("struct-array read expects a single index expression")
    index_code = codegen._emit_expr(
        index_expr,
        params,
        locals_info,
        "d1",
        "d2",
        target_type="int",
        frame_reg=frame_reg,
    )
    from .indexed_address import index_may_clobber_address_register
    if index_may_clobber_address_register(index_expr):
        code.extend(index_code)
        code.append(f"    lea {name},a0")
    else:
        code.append(f"    lea {name},a0")
        code.extend(index_code)

    prelude, operand = codegen._lower_indexed_address("a0", "d1", stride)
    code.extend(prelude)
    if field_offset:
        code.append(codegen._emit_add_immediate("    ", "d1", field_offset))

    if field_suffix in (".b", ".w") and reg_left == "d1":
        code.append(f"    move{field_suffix} {operand},d1")
        mask = "#$FF" if field_suffix == ".b" else "#$FFFF"
        code.append(f"    and.l {mask},d1")
    else:
        if field_suffix in (".b", ".w"):
            code.append(f"    clr.l {reg_left}")
        code.append(f"    move{field_suffix} {operand},{reg_left}")
    return code


def emit_array_address_of(codegen, name, index_expr, params, locals_info,
                          reg_left, reg_right, frame_reg, elem_bytes):
    """Emit code for &array[index] with centralized address lowering.

    Args:
        codegen: CodeGen instance
        name: Array variable name
        index_expr: AST expression for array index
        params: Procedure parameters
        locals_info: Local variable info
        reg_left: Target register for result address (e.g., 'a0')
        reg_right: Temporary register for index
        frame_reg: Frame pointer register
        elem_bytes: Element size in bytes

    Returns:
        List of assembly instruction strings.

    Note: Result is placed in 'a0' address register (not 'd0' data register).
    """
    code = []

    from . import ast

    if isinstance(index_expr, ast.Number):
        code.append(f"    lea {name},a0")
        # Constant index: compute offset at compile time
        index_val = index_expr.value
        offset = index_val * elem_bytes

        if offset == 0:
            # Address is just the base (already in a0)
            # Move a0 to the result register if needed
            if reg_left != "a0":
                code.append(f"    move.l a0,{reg_left}")
        else:
            # LEA writes address registers only; move the result when the
            # expression target is a data register.
            code.append(f"    lea {offset}(a0),a0")
            if reg_left != "a0":
                code.append(f"    move.l a0,{reg_left}")
    else:
        # Variable index: use centralized address lowering
        # Evaluate index into reg_right
        index_code = codegen._emit_expr(index_expr, params, locals_info,
                                        reg_right, "d2", target_type="int", frame_reg=frame_reg)
        from .indexed_address import index_may_clobber_address_register
        if index_may_clobber_address_register(index_expr):
            code.extend(index_code)
            code.append(f"    lea {name},a0")
        else:
            code.append(f"    lea {name},a0")
            code.extend(index_code)

        # Get prelude and operand from centralized helper
        prelude, operand = codegen._lower_indexed_address("a0", reg_right, elem_bytes)
        code.extend(prelude)

        # LEA preserves the address-of condition-code behavior of the original
        # 68000 lowering and also consumes future scaled operands directly.
        code.append(f"    lea {operand},a0")

        # Move result to target register if needed
        if reg_left != "a0":
            code.append(f"    move.l a0,{reg_left}")

    return code


def emit_array_store(codegen, name, index_expr, params, locals_info,
                     reg_value, reg_right, frame_reg, elem_bytes):
    """Emit a 1D global-array store through centralized indexed lowering.

    The caller evaluates the RHS before invoking this helper so address scratch
    registers remain available for nested expressions and calls.
    """
    code = []
    index_code = codegen._emit_expr(
        index_expr,
        params,
        locals_info,
        reg_right,
        "d2",
        target_type="int",
        frame_reg=frame_reg,
    )
    from .indexed_address import index_may_clobber_address_register
    if index_may_clobber_address_register(index_expr):
        code.extend(index_code)
        code.append(f"    lea {name},a0")
    else:
        code = [f"    lea {name},a0"]
        code.extend(index_code)

    prelude, operand = codegen._lower_indexed_address(
        "a0", reg_right, elem_bytes, use_scaled=True
    )
    code.extend(prelude)
    from . import ast
    code.append(f"    move{ast.size_suffix(elem_bytes)} {reg_value},{operand}")
    return code


def emit_struct_array_store(codegen, name, index_expr, params, locals_info,
                            reg_value, reg_right, frame_reg, stride,
                            field_offset, field_suffix):
    """Emit a struct-array member store after the RHS has been evaluated."""
    code = []
    index_code = codegen._emit_expr(
        index_expr,
        params,
        locals_info,
        reg_right,
        "d2",
        target_type="int",
        frame_reg=frame_reg,
    )
    from .indexed_address import index_may_clobber_address_register
    if index_may_clobber_address_register(index_expr):
        code.extend(index_code)
        code.append(f"    lea {name},a0")
    else:
        code = [f"    lea {name},a0"]
        code.extend(index_code)

    prelude, operand = codegen._lower_indexed_address("a0", reg_right, stride)
    code.extend(prelude)
    if field_offset:
        code.append(codegen._emit_add_immediate("    ", reg_right, field_offset))
    code.append(f"    move{field_suffix} {reg_value},{operand}")
    return code


def emit_2d_array_read(codegen, name, row_expr, col_expr, params, locals_info,
                       reg_left, frame_reg, elem_size, elem_bytes, col_count):
    """Emit a dynamic 2D read while centralizing final element scaling."""
    code = [f"    ; 2D array access: {name}"]
    row_code = codegen._emit_expr(
        row_expr, params, locals_info, "d1", "d2",
        target_type="int", frame_reg=frame_reg,
    )
    code.extend(row_code)
    code.append("    move.l d1,d2  ; save row")

    col_code = codegen._emit_expr(
        col_expr, params, locals_info, "d1", "a0",
        target_type="int", frame_reg=frame_reg,
    )
    code.extend(col_code)
    code.append(f"    mulu.w #{col_count},d2  ; row * col_count")
    code.append("    add.l d1,d2   ; + col")
    code.append(f"    lea {name},a0")

    prelude, operand = codegen._lower_indexed_address("a0", "d2", elem_bytes)
    code.extend(prelude)
    code.append(f"    move{'.' + elem_size} {operand},{reg_left}")
    return code


def emit_2d_array_store(codegen, name, row_expr, col_expr, params, locals_info,
                        reg_value, frame_reg, elem_size, elem_bytes, col_count):
    """Emit a dynamic 2D store after the caller has evaluated the RHS."""
    code = []
    from .indexed_address import index_may_clobber_address_register
    defer_base = (
        index_may_clobber_address_register(row_expr)
        or index_may_clobber_address_register(col_expr)
    )
    row_code = codegen._emit_expr(
        row_expr, params, locals_info, "d1", "d2",
        target_type="int", frame_reg=frame_reg,
    )
    if not defer_base:
        code.append(f"    lea {name},a0")
    code.extend(row_code)
    code.append("    move.l d1,d2  ; save row")

    col_code = codegen._emit_expr(
        col_expr, params, locals_info, "d1", "d3",
        target_type="int", frame_reg=frame_reg,
    )
    code.extend(col_code)
    if defer_base:
        code.append(f"    lea {name},a0")
    code.append(f"    mulu.w #{col_count},d2")
    code.append("    add.l d1,d2")

    prelude, operand = codegen._lower_indexed_address("a0", "d2", elem_bytes)
    code.extend(prelude)
    code.append(f"    move{'.' + elem_size} {reg_value},{operand}")
    return code


def emit_2d_array_address_of(codegen, name, row_expr, col_expr, params,
                             locals_info, reg_left, frame_reg, elem_bytes,
                             col_count):
    """Emit ``&array[row][col]`` with shared final element scaling."""
    from .indexed_address import index_may_clobber_address_register

    defer_base = (
        index_may_clobber_address_register(row_expr)
        or index_may_clobber_address_register(col_expr)
    )
    code = []
    if not defer_base:
        code.append(f"    lea {name},a0")
    row_code = codegen._emit_expr(
        row_expr, params, locals_info, "d1", "d2",
        target_type="int", frame_reg=frame_reg,
    )
    code.extend(row_code)
    code.append("    move.l d1,d2")
    col_code = codegen._emit_expr(
        col_expr, params, locals_info, "d1", "a1",
        target_type="int", frame_reg=frame_reg,
    )
    code.extend(col_code)
    if defer_base:
        code.append(f"    lea {name},a0")
    code.append(f"    mulu.w #{col_count},d2")
    code.append("    add.l d1,d2")

    prelude, operand = codegen._lower_indexed_address("a0", "d2", elem_bytes)
    code.extend(prelude)
    if "*" in operand:
        code.append(f"    lea {operand},a0")
    else:
        code.append("    add.l d2,a0")
    if reg_left != "a0":
        code.append(f"    move.l a0,{reg_left}")
    return code
