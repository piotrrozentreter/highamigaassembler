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
    
    # Load array base address into a0
    code.append(f"    lea {name},a0")
    
    # Evaluate index expression into reg_right (typically d1)
    index_code = codegen._emit_expr(index_expr, params, locals_info, 
                                    reg_right, "d2", target_type="int", frame_reg=frame_reg)
    code.extend(index_code)
    
    # Get prelude and operand from centralized address-lowering helper
    # elem_bytes is the stride (element size in bytes)
    prelude, operand = codegen._lower_indexed_address("a0", reg_right, elem_bytes)
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
    
    # Load pointer into a0
    if name.startswith('-') or '(' in name:
        # Local variable offset notation
        code.append(f"    move.l {name},a0")
    else:
        # Global variable name
        code.append(f"    move.l {name},a0")
    
    if isinstance(index_expr, ast.Number):
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
        code.extend(index_code)
        
        # Get prelude and operand from centralized helper
        prelude, operand = codegen._lower_indexed_address("a0", reg_right, elem_bytes)
        code.extend(prelude)
        
        # Load element with correct size
        size_suffix = ast.size_suffix(elem_bytes)
        code.append(f"    move{size_suffix} {operand},{reg_left}")
    
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
    
    code.append(f"    lea {name},a0")
    
    if isinstance(index_expr, ast.Number):
        # Constant index: compute offset at compile time
        index_val = index_expr.value
        offset = index_val * elem_bytes
        
        if offset == 0:
            # Address is just the base (already in a0)
            # Move a0 to the result register if needed
            if reg_left != "a0":
                code.append(f"    move.l a0,{reg_left}")
        else:
            # Add offset to base address
            code.append(f"    lea {offset}(a0),{reg_left}")
    else:
        # Variable index: use centralized address lowering
        # Evaluate index into reg_right
        index_code = codegen._emit_expr(index_expr, params, locals_info,
                                        reg_right, "d2", target_type="int", frame_reg=frame_reg)
        code.extend(index_code)
        
        # Get prelude and operand from centralized helper
        prelude, operand = codegen._lower_indexed_address("a0", reg_right, elem_bytes)
        code.extend(prelude)
        
        # Use LEA to calculate the final address
        # operand is something like "(a0,d1.l)" or "(a0,d1.l*4)"
        code.append(f"    lea {operand},a0")
        
        # Move result to target register if needed
        if reg_left != "a0":
            code.append(f"    move.l a0,{reg_left}")
    
    return code
