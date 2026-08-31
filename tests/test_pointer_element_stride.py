"""Indexing through a typed pointer must stride by the pointee's own size.

``p[i]`` scales the index in ``d1`` (or, on ``--cpu 68020``, in the addressing
mode's scale factor). Stride, load width and sign-extension must all be derived
from the same pointee lookup: a stride that disagrees with the element size
silently reads or writes the wrong object, and a write that strides differently
from the matching read corrupts memory with no diagnostic at compile, assemble
or run time.
"""

import re

import pytest

from hasc import codegen, parser, validator
from hasc.target import CpuTarget, TargetSpec


BASELINE = TargetSpec.for_cpu(CpuTarget.M68000)
TARGET_68020 = TargetSpec.for_cpu(CpuTarget.M68020)
TARGETS = (BASELINE, TARGET_68020)


SCALAR_SOURCE = """
code main:
    proc rd_i8(p: i8*, i: int) -> int { return p[i]; }
    proc rd_u8(p: u8*, i: int) -> int { return p[i]; }
    proc rd_i16(p: i16*, i: int) -> int { return p[i]; }
    proc rd_u16(p: u16*, i: int) -> int { return p[i]; }
    proc rd_i32(p: i32*, i: int) -> int { return p[i]; }
    proc entry() -> long { return 0; }
"""

SCALAR_ORDER = ["rd_i8", "rd_u8", "rd_i16", "rd_u16", "rd_i32", "entry"]


# Ent is 6 bytes - not a power of two, so the stride cannot hide in a shift or
# in the 68020 scale factor. Small is 2 bytes, where a wrong "long" stride would
# still look plausible. USmall is the same size but holds an unsigned field.
STRUCT_SOURCE = """
bss stride_bss:
    struct Ent[8] { x: i16, y: i16, z: i16 }
    struct Small[8] { a: i16 }
    struct USmall[8] { a: u16 }

code main:
    proc rd_ent_ptr(p: Ent*, i: int) -> int { return p[i].y; }
    proc wr_ent_ptr(p: Ent*, i: int, v: int) -> void { p[i].y = v; }
    proc rd_ent_arr(i: int) -> int { return Ent[i].y; }
    proc wr_ent_arr(i: int, v: int) -> void { Ent[i].y = v; }
    proc rd_small_ptr(p: Small*, i: int) -> int { return p[i].a; }
    proc wr_small_ptr(p: Small*, i: int, v: int) -> void { p[i].a = v; }
    proc rd_small_arr(i: int) -> int { return Small[i].a; }
    proc wr_small_arr(i: int, v: int) -> void { Small[i].a = v; }
    proc rd_usmall_ptr(p: USmall*, i: int) -> int { return p[i].a; }
    proc entry() -> long { return 0; }
"""

STRUCT_ORDER = [
    "rd_ent_ptr", "wr_ent_ptr", "rd_ent_arr", "wr_ent_arr",
    "rd_small_ptr", "wr_small_ptr", "rd_small_arr", "wr_small_arr",
    "rd_usmall_ptr", "entry",
]


def _bodies(source, order, target):
    asm = codegen.CodeGen(parser.parse(source), target).gen()
    out = {}
    bounds = order + [None]
    for name, nxt in zip(bounds, bounds[1:]):
        start = asm.index(f"\n{name}:")
        end = asm.index(f"\n{nxt}:") if nxt else len(asm)
        out[name] = asm[start:end]
    return out


def _lines(body):
    return [ln.strip() for ln in body.splitlines()]


SHIFT_RE = re.compile(r"^lsl\.l #(\d+),d1$")
MUL_RE = re.compile(r"^mulu?\.[wl] #(\d+),d1$")
DOUBLE_RE = re.compile(r"^add\.l d1,d1$")
OPERAND_RE = re.compile(r"-?[\w$]*\(a\d,d1\.l(?:\*(\d))?\)")
FIELD_OFFSET_RE = re.compile(r"^add(?:q|i)?\.l #\d+,d1$")


def _explicit_scale_ops(body):
    """Instructions that scale the index register. Field-offset adds
    (``addq.l #2,d1``) are deliberately not scale ops."""
    return [ln for ln in _lines(body)
            if SHIFT_RE.match(ln) or MUL_RE.match(ln) or DOUBLE_RE.match(ln)]


def _operand_scale(body):
    """Scale factor folded into the indexed addressing mode (always 1 on 68000)."""
    for ln in _lines(body):
        m = OPERAND_RE.search(ln)
        if m:
            return int(m.group(1)) if m.group(1) else 1
    raise AssertionError(f"no indexed operand in:\n{body}")


def _index_scale(body):
    """Total factor the index is multiplied by, however the target spells it."""
    scale = _operand_scale(body)
    for ln in _explicit_scale_ops(body):
        m = SHIFT_RE.match(ln)
        if m:
            scale *= 1 << int(m.group(1))
            continue
        m = MUL_RE.match(ln)
        if m:
            scale *= int(m.group(1))
            continue
        scale *= 2
    return scale


def _element_address(body):
    """(scale ops, index adjustments, operand) - the whole address form."""
    lines = _lines(body)
    operand = next(m.group(0) for m in (OPERAND_RE.search(ln) for ln in lines) if m)
    return (_explicit_scale_ops(body),
            [ln for ln in lines if FIELD_OFFSET_RE.match(ln)],
            operand)


def _sign_extend_ops(target, dest, suffix):
    if suffix == ".b":
        ops = ["extb.l"] if target.supports_extb_l else ["ext.w", "ext.l"]
    else:
        ops = ["ext.l"]
    return [f"{op} {dest}" for op in ops]


# --- Scalar pointees ---------------------------------------------------------

@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,elem_bytes,suffix,extension", [
    ("rd_i8", 1, ".b", "sign"),
    ("rd_u8", 1, ".b", "zero"),
    ("rd_i16", 2, ".w", "sign"),
    ("rd_u16", 2, ".w", "zero"),
    ("rd_i32", 4, ".l", "none"),
])
def test_scalar_pointee_stride_width_and_extension(target, proc, elem_bytes, suffix, extension):
    """Stride, load width and extension must all agree with the pointee type."""
    body = _bodies(SCALAR_SOURCE, SCALAR_ORDER, target)[proc]
    assert _index_scale(body) == elem_bytes, body

    lines = _lines(body)
    load = next(ln for ln in lines if ln.startswith(f"move{suffix} ") and "(a0" in ln)
    dest = load.split(",")[-1]
    idx = lines.index(load)
    if extension == "sign":
        expected = _sign_extend_ops(target, dest, suffix)
        assert lines[idx + 1:idx + 1 + len(expected)] == expected, body
    elif extension == "zero":
        assert lines[idx - 1] == f"clr.l {dest}", body
    else:
        for op in ("ext.l", "ext.w", "extb.l", "clr.l", "andi.l"):
            assert op not in body, body


@pytest.mark.parametrize("proc,ops", [
    ("rd_i8", []),
    ("rd_u8", []),
    ("rd_i16", ["lsl.l #1,d1"]),
    ("rd_u16", ["lsl.l #1,d1"]),
    ("rd_i32", ["lsl.l #2,d1"]),
])
def test_scalar_pointee_stride_instructions_on_68000(proc, ops):
    """Pin the baseline instruction form. The 68020 folds these into the
    addressing mode's scale factor, which the test above accounts for."""
    body = _bodies(SCALAR_SOURCE, SCALAR_ORDER, BASELINE)[proc]
    assert _explicit_scale_ops(body) == ops, body
    assert _operand_scale(body) == 1, body


# --- Struct pointees ---------------------------------------------------------

@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,struct_size", [
    ("rd_ent_ptr", 6),
    ("wr_ent_ptr", 6),
    ("rd_small_ptr", 2),
    ("wr_small_ptr", 2),
])
def test_struct_pointee_strides_by_struct_size(target, proc, struct_size):
    body = _bodies(STRUCT_SOURCE, STRUCT_ORDER, target)[proc]
    assert _index_scale(body) == struct_size, body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc", ["rd_ent_ptr", "wr_ent_ptr"])
def test_six_byte_struct_stride_uses_an_explicit_multiply(target, proc):
    """6 is not a legal scale factor on either target, so the stride must stay
    an explicit ``mulu.w #6``."""
    body = _bodies(STRUCT_SOURCE, STRUCT_ORDER, target)[proc]
    assert _explicit_scale_ops(body) == ["mulu.w #6,d1"], body
    assert _operand_scale(body) == 1, body


@pytest.mark.parametrize("proc", ["rd_small_ptr", "wr_small_ptr"])
def test_two_byte_struct_stride_instruction_on_68000(proc):
    body = _bodies(STRUCT_SOURCE, STRUCT_ORDER, BASELINE)[proc]
    assert _explicit_scale_ops(body) == ["lsl.l #1,d1"], body


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("ptr_proc,arr_proc", [
    ("rd_ent_ptr", "rd_ent_arr"),
    ("wr_ent_ptr", "wr_ent_arr"),
    ("rd_small_ptr", "rd_small_arr"),
    ("wr_small_ptr", "wr_small_arr"),
])
def test_pointer_and_array_indexing_use_the_same_stride(target, ptr_proc, arr_proc):
    """``p[i].field`` and ``arr[i].field`` walk the same layout, so they must
    scale the index identically."""
    bodies = _bodies(STRUCT_SOURCE, STRUCT_ORDER, target)
    ptr_body, arr_body = bodies[ptr_proc], bodies[arr_proc]
    assert _explicit_scale_ops(ptr_body) == _explicit_scale_ops(arr_body), (ptr_body, arr_body)
    assert _index_scale(ptr_body) == _index_scale(arr_body), (ptr_body, arr_body)


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_struct_pointer_loads_base_value_while_array_takes_its_address(target):
    bodies = _bodies(STRUCT_SOURCE, STRUCT_ORDER, target)
    assert "move.l 8(a6),a0" in bodies["rd_ent_ptr"], bodies["rd_ent_ptr"]
    assert "lea " not in bodies["rd_ent_ptr"], bodies["rd_ent_ptr"]
    assert "lea Ent,a0" in bodies["rd_ent_arr"], bodies["rd_ent_arr"]


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_struct_pointee_takes_no_sign_extension_path(target):
    """A struct has no signedness. Any extension must come from the accessed
    field's type, never from the pointee name being run through is_signed()."""
    bodies = _bodies(STRUCT_SOURCE, STRUCT_ORDER, target)

    signed_field = bodies["rd_small_ptr"]
    assert "ext.l d0" in signed_field, signed_field

    unsigned_field = bodies["rd_usmall_ptr"]
    for op in ("ext.l", "ext.w", "extb.l"):
        assert op not in unsigned_field, unsigned_field
    assert "clr.l d0" in unsigned_field, unsigned_field

    # Same size, different field signedness: identical stride, different extension.
    assert _index_scale(signed_field) == _index_scale(unsigned_field) == 2

    # A 6-byte pointee holding word fields must not gain a long load either.
    ent = bodies["rd_ent_ptr"]
    assert "move.l (a0" not in ent and "move.l 2(a0" not in ent, ent


# --- Read/write symmetry -----------------------------------------------------

@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("read_proc,write_proc", [
    ("rd_ent_ptr", "wr_ent_ptr"),
    ("rd_small_ptr", "wr_small_ptr"),
])
def test_read_and_write_through_pointer_use_the_same_stride(target, read_proc, write_proc):
    """An asymmetric stride would make ``p[i].f = v`` write to a different
    object than ``v = p[i].f`` reads - silent memory corruption."""
    bodies = _bodies(STRUCT_SOURCE, STRUCT_ORDER, target)
    read, write = bodies[read_proc], bodies[write_proc]
    assert _index_scale(read) == _index_scale(write), (read, write)


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("read_proc,write_proc", [
    ("rd_ent_ptr", "wr_ent_ptr"),
    ("rd_small_ptr", "wr_small_ptr"),
])
def test_read_and_write_use_the_same_element_address(target, read_proc, write_proc):
    """Stride alone is not enough: the field displacement and the final operand
    must match too."""
    bodies = _bodies(STRUCT_SOURCE, STRUCT_ORDER, target)
    read, write = bodies[read_proc], bodies[write_proc]
    assert _element_address(read) == _element_address(write), (read, write)


# --- Rejected shapes ---------------------------------------------------------

VOID_READ = """
code main:
    proc rd(p: void*, i: int) -> int { return p[i]; }
    proc entry() -> long { return 0; }
"""

VOID_WRITE = """
code main:
    proc wr(p: void*, i: int, v: int) -> void { p[i] = v; }
    proc entry() -> long { return 0; }
"""


@pytest.mark.parametrize("source,proc", [(VOID_READ, "rd"), (VOID_WRITE, "wr")])
def test_void_pointer_indexing_is_a_validation_error(source, proc):
    """No stride is derivable from ``void*``, so it must be diagnosed rather
    than silently guessed at."""
    module = parser.parse(source)
    with pytest.raises(validator.ValidationError) as exc:
        validator.Validator(module).validate()
    message = str(exc.value)
    assert f"In proc '{proc}': Cannot index through 'void*' variable 'p'" in message
    assert "the element size is undefined" in message
    assert "byte*" in message and "int*" in message


WHOLE_STRUCT = """
bss whole_bss:
    struct Ent[8] { x: i16, y: i16, z: i16 }

code main:
    proc rd(p: Ent*, i: int) -> int { return p[i]; }
    proc entry() -> long { return 0; }
"""


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_whole_struct_through_pointer_index_is_rejected(target):
    module = parser.parse(WHOLE_STRUCT)
    with pytest.raises(codegen.CodeGenError, match="Cannot load whole struct 'Ent'"):
        codegen.CodeGen(module, target).gen()


# --- &p[i] -------------------------------------------------------------------

ADDR_SOURCE = """
code main:
    proc addr_i16(p: i16*, i: int) -> int { return &p[i]; }
    proc rd_i16(p: i16*, i: int) -> int { return p[i]; }
    proc addr_i32(p: i32*, i: int) -> int { return &p[i]; }
    proc rd_i32(p: i32*, i: int) -> int { return p[i]; }
    proc entry() -> long { return 0; }
"""

ADDR_ORDER = ["addr_i16", "rd_i16", "addr_i32", "rd_i32", "entry"]


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("addr_proc,read_proc,elem_bytes", [
    ("addr_i16", "rd_i16", 2),
    ("addr_i32", "rd_i32", 4),
])
def test_address_of_element_matches_element_read(target, addr_proc, read_proc, elem_bytes):
    """``&p[i]`` must name the address that ``p[i]`` reads from."""
    bodies = _bodies(ADDR_SOURCE, ADDR_ORDER, target)
    addr, read = bodies[addr_proc], bodies[read_proc]
    assert _index_scale(addr) == elem_bytes, addr
    assert _index_scale(addr) == _index_scale(read), (addr, read)
    assert _explicit_scale_ops(addr) == _explicit_scale_ops(read), (addr, read)
