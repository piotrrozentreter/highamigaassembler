"""Pure indexed effective-address lowering for Motorola CPU targets."""

from typing import List, Optional, Tuple

from .target import TargetSpec


LoweredAddress = Tuple[List[str], str]


def index_may_clobber_address_register(expr) -> bool:
    """Return whether evaluating an index may overwrite the address scratch."""
    from . import ast

    if isinstance(expr, (ast.Call, ast.ArrayAccess, ast.MemberAccess)):
        return True
    if isinstance(expr, ast.BinOp):
        return index_may_clobber_address_register(expr.left) or index_may_clobber_address_register(expr.right)
    if isinstance(expr, ast.UnaryOp):
        return index_may_clobber_address_register(expr.operand)
    return False


def _scaled_operand(base_reg: str, index_reg: str, scale: Optional[int]) -> str:
    index = f"{index_reg}.l"
    if scale is not None:
        index += f"*{scale}"
    return f"({base_reg},{index})"


def _full_width_stride_fallback(index_reg: str, stride: int, scratch_reg: str) -> List[str]:
    """Multiply an index by a large constant without 16-bit truncation.

    Horner-style shift/add lowering keeps the original index in scratch_reg and
    accumulates the product in index_reg, so only two data registers are needed.
    """
    if stride <= 0:
        raise ValueError(f"Stride must be positive, got {stride}")
    if scratch_reg == index_reg:
        scratch_reg = "d3" if index_reg != "d3" else "d2"

    lines = [f"    move.l {index_reg},{scratch_reg}", f"    clr.l {index_reg}"]
    highest_bit = stride.bit_length() - 1
    for bit in range(highest_bit, -1, -1):
        if bit != highest_bit:
            lines.append(f"    lsl.l #1,{index_reg}")
        if stride & (1 << bit):
            lines.append(f"    add.l {scratch_reg},{index_reg}")
    return lines


def emit_full_width_multiply(index_reg: str, multiplier: int,
                             scratch_reg: str = "d3") -> List[str]:
    """Multiply a long index by a constant without truncating its high word."""
    return _full_width_stride_fallback(index_reg, multiplier, scratch_reg)


def lower_indexed_address(
    target: TargetSpec,
    base_reg: str,
    index_reg: str,
    stride: int,
    displacement: int = 0,
    scratch_reg: str = "d2",
    enable_scaled: bool = False,
) -> LoweredAddress:
    """Return prelude instructions and a legal indexed operand.

    Indexes remain long-sized. Scales 1, 2, 4, and 8 use 68020 syntax only
    when the selected target supports it. Smaller arbitrary strides preserve
    the existing 68000 ``mulu.w`` behavior; larger strides use full-width
    shift/add arithmetic instead of truncating through ``mulu.w``.
    """
    if stride <= 0:
        raise ValueError(f"Stride must be positive, got {stride}")
    if (
        displacement
        and enable_scaled
        and target.supports_scaled_index
        and not -128 <= displacement <= 127
    ):
        raise ValueError(
            "Scaled indexed displacement must fit signed 8-bit brief form"
        )

    prelude: List[str] = []
    scale: Optional[int] = None
    if stride in (1, 2, 4, 8):
        if enable_scaled and target.supports_scaled_index:
            scale = stride if stride != 1 else None
        elif stride != 1:
            shift = {2: 1, 4: 2, 8: 3}[stride]
            prelude.append(f"    lsl.l #{shift},{index_reg}")
    elif stride in (16, 32):
        shift = {16: 4, 32: 5}[stride]
        prelude.append(f"    lsl.l #{shift},{index_reg}")
    elif stride <= 32767:
        prelude.append(f"    mulu.w #{stride},{index_reg}")
    else:
        prelude.extend(_full_width_stride_fallback(index_reg, stride, scratch_reg))

    operand = _scaled_operand(base_reg, index_reg, scale)
    if displacement:
        operand = f"{displacement}{operand}"
        operand = operand.replace(str(displacement) + "(", f"{displacement}(", 1)
    return prelude, operand
