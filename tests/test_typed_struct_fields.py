"""Typed struct fields (``name: type``) carry width AND signedness.

The legacy ``name.b`` / ``name.w`` / ``name.l`` form only ever carried a width,
so its reads zero-extend. The opt-in typed form additionally records signedness,
so a signed narrow field must sign-extend at every read site. These tests pin
both behaviours, on both CPU targets.
"""

import pytest

from hasc import ast, codegen, parser
from hasc.target import CpuTarget, TargetSpec


BASELINE = TargetSpec.for_cpu(CpuTarget.M68000)
TARGET_68020 = TargetSpec.for_cpu(CpuTarget.M68020)
TARGETS = (BASELINE, TARGET_68020)


SOURCE = """
bss probe:
    struct s { legacy_b.b, legacy_w.w, sb: i8, sw: i16, ub: u8, uw: u16, sl: i32 }
    struct arr[4] { sb: i8, sw: i16, ub: u8, uw: u16, legacy_w.w }

code main:
    proc v_legacy_b() -> int { return s.legacy_b; }
    proc v_legacy_w() -> int { return s.legacy_w; }
    proc v_sb() -> int { return s.sb; }
    proc v_sw() -> int { return s.sw; }
    proc v_ub() -> int { return s.ub; }
    proc v_uw() -> int { return s.uw; }
    proc v_sl() -> int { return s.sl; }
    proc p_legacy_b(p: s*) -> int { return p->legacy_b; }
    proc p_legacy_w(p: s*) -> int { return p->legacy_w; }
    proc p_sb(p: s*) -> int { return p->sb; }
    proc p_sw(p: s*) -> int { return p->sw; }
    proc p_ub(p: s*) -> int { return p->ub; }
    proc p_uw(p: s*) -> int { return p->uw; }
    proc a_legacy_w(i: int) -> int { return arr[i].legacy_w; }
    proc a_sb(i: int) -> int { return arr[i].sb; }
    proc a_sw(i: int) -> int { return arr[i].sw; }
    proc a_ub(i: int) -> int { return arr[i].ub; }
    proc a_uw(i: int) -> int { return arr[i].uw; }
    proc alias_uw(i: int, acc: int) -> int { return acc + arr[i].uw; }
    proc alias_sw(i: int, acc: int) -> int { return acc + arr[i].sw; }
    proc end() -> int { return 0; }
"""

PROC_ORDER = [
    "v_legacy_b", "v_legacy_w", "v_sb", "v_sw", "v_ub", "v_uw", "v_sl",
    "p_legacy_b", "p_legacy_w", "p_sb", "p_sw", "p_ub", "p_uw",
    "a_legacy_w", "a_sb", "a_sw", "a_ub", "a_uw",
    "alias_uw", "alias_sw", "end",
]


def _bodies(target):
    asm = codegen.CodeGen(parser.parse(SOURCE), target).gen()
    out = {}
    for name, nxt in zip(PROC_ORDER, PROC_ORDER[1:]):
        start = asm.index(f"\n{name}:")
        end = asm.index(f"\n{nxt}:")
        out[name] = [ln.strip() for ln in asm[start:end].splitlines()]
    return out


def _sign_extend_ops(target, suffix):
    if suffix == ".w":
        return ["ext.l"]
    return ["extb.l"] if target.supports_extb_l else ["ext.w", "ext.l"]


def _load_index(lines, suffix):
    for i, ln in enumerate(lines):
        if ln.startswith(f"move{suffix} ") and not ln.startswith(f"move{suffix} #"):
            return i
    raise AssertionError(f"no move{suffix} load in {lines}")


# --- Parser -----------------------------------------------------------------

def test_typed_field_records_type_size_and_signedness():
    module = parser.parse(SOURCE)
    struct = next(v for item in module.items if hasattr(item, 'variables')
                  for v in item.variables
                  if isinstance(v, ast.StructVarDecl) and v.name == "s")
    fields = {f.name: f for f in struct.fields}

    assert (fields["sb"].type_name, fields["sb"].size_suffix, fields["sb"].signed) == ("i8", "b", True)
    assert (fields["sw"].type_name, fields["sw"].size_suffix, fields["sw"].signed) == ("i16", "w", True)
    assert (fields["ub"].type_name, fields["ub"].size_suffix, fields["ub"].signed) == ("u8", "b", False)
    assert (fields["uw"].type_name, fields["uw"].size_suffix, fields["uw"].signed) == ("u16", "w", False)
    assert (fields["sl"].type_name, fields["sl"].size_suffix, fields["sl"].signed) == ("i32", "l", True)


def test_legacy_suffix_fields_stay_untyped_and_unsigned():
    module = parser.parse(SOURCE)
    struct = next(v for item in module.items if hasattr(item, 'variables')
                  for v in item.variables
                  if isinstance(v, ast.StructVarDecl) and v.name == "s")
    fields = {f.name: f for f in struct.fields}
    for name, suffix in (("legacy_b", "b"), ("legacy_w", "w")):
        assert fields[name].type_name is None
        assert fields[name].signed is False
        assert fields[name].size_suffix == suffix


@pytest.mark.parametrize("type_name,expected", [
    ("byte", ("b", True)), ("i8", ("b", True)), ("u8", ("b", False)),
    ("word", ("w", True)), ("i16", ("w", True)), ("u16", ("w", False)),
    ("short", ("w", True)), ("UWORD", ("w", False)), ("WORD", ("w", True)),
    ("int", ("l", True)), ("u32", ("l", False)), ("ULONG", ("l", False)),
])
def test_typed_field_widths_and_signedness_follow_the_type_table(type_name, expected):
    module = parser.parse(f"""
bss probe:
    struct t {{ f: {type_name} }}

code main:
    proc end() -> int {{ return 0; }}
""")
    struct = next(v for item in module.items if hasattr(item, 'variables')
                  for v in item.variables if isinstance(v, ast.StructVarDecl))
    field = struct.fields[0]
    assert (field.size_suffix, field.signed) == expected


# --- Validator ---------------------------------------------------------------

def test_unknown_struct_field_type_is_rejected():
    from hasc import validator
    module = parser.parse("""
bss probe:
    struct z { f: notatype }

code main:
    proc end() -> int { return 0; }
""")
    with pytest.raises(validator.ValidationError) as exc:
        validator.Validator(module).validate()
    assert "Unknown type 'notatype' for struct field 'z.f' (line 3)" in str(exc.value)


def test_void_struct_field_type_is_rejected():
    from hasc import validator
    module = parser.parse("""
bss probe:
    struct z { f: void }

code main:
    proc end() -> int { return 0; }
""")
    with pytest.raises(validator.ValidationError) as exc:
        validator.Validator(module).validate()
    assert "not a valid struct field type for 'z.f'" in str(exc.value)


def test_legacy_suffix_fields_are_not_type_checked():
    from hasc import validator
    module = parser.parse(SOURCE)
    warnings = validator.Validator(module).validate()
    assert not [w for w in warnings if "struct field" in w], warnings


# --- Codegen: all three read sites ------------------------------------------

SIGNED_CASES = [
    ("v_sb", ".b"), ("v_sw", ".w"),
    ("p_sb", ".b"), ("p_sw", ".w"),
    ("a_sb", ".b"), ("a_sw", ".w"),
]

UNSIGNED_CASES = [
    ("v_ub", ".b"), ("v_uw", ".w"),
    ("p_ub", ".b"), ("p_uw", ".w"),
    ("a_ub", ".b"), ("a_uw", ".w"),
]


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,suffix", SIGNED_CASES)
def test_signed_typed_fields_sign_extend(target, proc, suffix):
    lines = _bodies(target)[proc]
    idx = _load_index(lines, suffix)
    dest = lines[idx].split(",")[-1]
    expected = [f"{op} {dest}" for op in _sign_extend_ops(target, suffix)]
    assert lines[idx + 1:idx + 1 + len(expected)] == expected, lines
    assert f"clr.l {dest}" not in lines[:idx], lines


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,suffix", UNSIGNED_CASES)
def test_unsigned_typed_fields_zero_extend(target, proc, suffix):
    lines = _bodies(target)[proc]
    idx = _load_index(lines, suffix)
    dest = lines[idx].split(",")[-1]
    mask = "#$FF" if suffix == ".b" else "#$FFFF"
    assert (lines[idx - 1] == f"clr.l {dest}"
            or lines[idx + 1] in (f"and.l {mask},{dest}", f"andi.l {mask},{dest}")), lines
    for op in ("ext.w", "ext.l", "extb.l"):
        assert f"{op} {dest}" not in lines, lines


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_68020_signed_byte_field_uses_extb_l(target):
    lines = _bodies(TARGET_68020)["v_sb"]
    assert any(ln.startswith("extb.l") for ln in lines), lines
    assert not any(ln.startswith("ext.w") for ln in lines), lines


def test_68000_signed_byte_field_uses_ext_pair():
    lines = _bodies(BASELINE)["v_sb"]
    assert not any(ln.startswith("extb.l") for ln in lines), lines
    assert [ln for ln in lines if ln.startswith(("ext.w", "ext.l"))][:2] == [
        "ext.w d0", "ext.l d0"], lines


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_long_typed_field_needs_no_extension(target):
    lines = _bodies(target)["v_sl"]
    for op in ("ext.w", "ext.l", "extb.l", "clr.l", "and.l", "andi.l"):
        assert not any(ln.startswith(op) for ln in lines), lines


# --- Codegen: aliasing (destination register == live index register) ---------

@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_unsigned_field_aliasing_index_register_masks_after_the_load(target):
    """`acc + arr[i].uw` loads into d1, which also holds the scaled index, so a
    pre-move clr.l would destroy the index; the mask must follow the load."""
    lines = _bodies(target)["alias_uw"]
    idx = _load_index(lines, ".w")
    load = lines[idx]
    assert load.endswith(",d1") and "(a0,d1" in load, lines
    assert lines[idx - 1] != "clr.l d1", lines
    assert lines[idx + 1] in ("and.l #$FFFF,d1", "andi.l #$FFFF,d1"), lines
    # The index is consumed by the load itself, so the accumulator in d0 survives.
    assert lines[idx + 2] == "add.l d1,d0", lines


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_signed_field_aliasing_index_register_sign_extends_after_the_load(target):
    lines = _bodies(target)["alias_sw"]
    idx = _load_index(lines, ".w")
    assert lines[idx].endswith(",d1") and "(a0,d1" in lines[idx], lines
    assert lines[idx - 1] != "clr.l d1", lines
    assert lines[idx + 1] == "ext.l d1", lines
    assert lines[idx + 2] == "add.l d1,d0", lines


# --- Byte-identity: legacy fields are unchanged ------------------------------

@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
@pytest.mark.parametrize("proc,suffix", [
    ("v_legacy_b", ".b"), ("v_legacy_w", ".w"),
    ("p_legacy_b", ".b"), ("p_legacy_w", ".w"),
])
def test_legacy_suffix_fields_still_zero_extend_with_a_hoisted_clr(target, proc, suffix):
    lines = _bodies(target)[proc]
    idx = _load_index(lines, suffix)
    dest = lines[idx].split(",")[-1]
    assert lines[idx - 1] == f"clr.l {dest}", lines
    for op in ("ext.w", "ext.l", "extb.l", "and.l", "andi.l"):
        assert not any(ln.startswith(op) for ln in lines), lines


@pytest.mark.parametrize("target", TARGETS, ids=("68000", "68020"))
def test_legacy_struct_array_field_still_zero_extends(target):
    lines = _bodies(target)["a_legacy_w"]
    idx = _load_index(lines, ".w")
    dest = lines[idx].split(",")[-1]
    assert lines[idx - 1] == f"clr.l {dest}", lines
    for op in ("ext.w", "ext.l", "extb.l"):
        assert not any(ln.startswith(op) for ln in lines), lines
