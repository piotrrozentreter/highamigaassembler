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


def index_fits_word_range(index_expr) -> bool:
    """Return True only when index_expr is a compile-time constant that fits
    a signed 16-bit range, the sole case Phase 2 proves safe for a `.w`
    index register (sign-extending the low word reproduces the full value).
    All other expressions must keep the conservative `.l` index size.
    """
    from . import ast

    return isinstance(index_expr, ast.Number) and -32768 <= index_expr.value <= 32767


def _scaled_operand(base_reg: str, index_reg: str, scale: Optional[int], index_size: str = "l") -> str:
    index = f"{index_reg}.{index_size}"
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
    index_word_safe: bool = False,
) -> LoweredAddress:
    """Return prelude instructions and a legal indexed operand.

    Indexes are long-sized by default. Scales 1, 2, 4, and 8 use 68020
    syntax only when the selected target supports it. Smaller arbitrary
    strides preserve the existing 68000 ``mulu.w`` behavior; larger strides
    use full-width shift/add arithmetic instead of truncating through
    ``mulu.w``.

    ``index_word_safe`` lets a caller assert (via `index_fits_word_range()`)
    that the index register provably holds a value within the signed 16-bit
    range, so the smaller `.w` index size can be used instead of `.l`. This
    is only applied on targets with `supports_scaled_index` (68020); the
    68000 path is unaffected regardless of this flag.

    Scaled displacements outside the signed 8-bit brief-form range
    (-128..127) are only legal when ``target.supports_full_index_extension``
    is True (68020 full-extension indexed addressing, e.g.
    ``1000(a0,d1.l*4)``); vasm selects the extension word width
    automatically, so no operand-format change is needed beyond allowing the
    larger displacement through. Targets without full-extension support
    (68000) must keep raising for out-of-range scaled displacements.
    """
    if stride <= 0:
        raise ValueError(f"Stride must be positive, got {stride}")
    if (
        displacement
        and not target.supports_full_index_extension
        and not -128 <= displacement <= 127
    ):
        raise ValueError(
            "Indexed displacement must fit signed 8-bit brief form"
        )

    prelude: List[str] = []
    scale: Optional[int] = None
    used_scaled_addressing = False
    if stride in (1, 2, 4, 8):
        if enable_scaled and target.supports_scaled_index:
            scale = stride if stride != 1 else None
            used_scaled_addressing = True
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

    # `.w` sizing is only sound when the true scaled-register addressing branch
    # was taken above: that is the only path where index_reg still holds the
    # original unmultiplied index value. Every other branch above overwrites
    # index_reg with index * stride, so index_word_safe (which only proves the
    # ORIGINAL index fits 16 bits) must not leak into operand sizing there.
    operand = _scaled_operand(
        base_reg,
        index_reg,
        scale,
        "w" if (index_word_safe and used_scaled_addressing) else "l",
    )
    if displacement:
        operand = f"{displacement}{operand}"
        operand = operand.replace(str(displacement) + "(", f"{displacement}(", 1)
    return prelude, operand
