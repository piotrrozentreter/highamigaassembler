"""Data-section array reservation and initializer emission (C2/C3).

C2: uninitialized typed arrays must reserve count * element_size.
C3: singleton / string / short braced inits must emit real dc.* data
    (not a zero-sized or empty ds.b reservation).
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hasc import parser as has_parser
from hasc import codegen as has_codegen
from hasc import validator as has_validator


def compile_src(src: str) -> str:
    mod = has_parser.parse(src)
    validator = has_validator.Validator(mod)
    validator.validate()
    validator.apply_resolutions()
    assert not validator.errors, validator.errors
    return has_codegen.CodeGen(mod).gen()


def section_body(asm: str, section_name: str) -> str:
    lines = asm.splitlines()
    start = next(
        (i for i, l in enumerate(lines) if re.search(rf"SECTION\s+{section_name}\b", l)),
        None,
    )
    assert start is not None, f"SECTION {section_name} not found"
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if re.match(r"\s*SECTION\b", lines[i]):
            end = i
            break
    return "\n".join(lines[start:end])


def test_uninit_word_array_reserves_element_size():
    asm = compile_src(
        """
data d:
    arr.w[4]
    after.b = 1
"""
    )
    body = section_body(asm, "d")
    assert re.search(r"arr:\s*\n\s+ds\.w\s+4\b", body), body
    assert "ds.b 4" not in body


def test_uninit_long_array_reserves_element_size():
    asm = compile_src(
        """
data d:
    arr.l[3]
"""
    )
    body = section_body(asm, "d")
    assert re.search(r"arr:\s*\n\s+ds\.l\s+3\b", body), body


def test_uninit_word_array_after_byte_gets_even_align():
    asm = compile_src(
        """
data d:
    lead.b = 1
    arr.w[2]
"""
    )
    body = section_body(asm, "d")
    assert "even" in body
    assert re.search(r"arr:\s*\n\s+ds\.w\s+2\b", body), body


def test_singleton_braced_init_emits_dc_and_pads():
    asm = compile_src(
        """
data d:
    bytes.b[4] = {1}
"""
    )
    body = section_body(asm, "d")
    assert "dc.b 1" in body
    assert re.search(r"dcb\.b\s+3,\s*0", body), body
    assert not re.search(r"bytes:\s*\n\s+ds\.b\s+4\b", body)


def test_string_byte_array_init_emits_dc_and_pads():
    asm = compile_src(
        """
data d:
    buf.b[6] = "Hi"
"""
    )
    body = section_body(asm, "d")
    assert 'dc.b "Hi"' in body
    assert re.search(r"dcb\.b\s+4,\s*0", body), body
    assert not re.search(r"buf:\s*\n\s+ds\.b\s+6\b", body)


def test_full_word_array_init_still_emits_dc_w():
    asm = compile_src(
        """
data d:
    words.w[4] = {1, 2, 3, 4}
"""
    )
    body = section_body(asm, "d")
    assert re.search(r"dc\.w\s+1,2,3,4", body), body


def test_bss_word_array_already_sized_by_elements():
    """BSS path was correct; guard against regressions."""
    asm = compile_src(
        """
bss b:
    arr.w[4]
    after.b:1
"""
    )
    body = section_body(asm, "b")
    assert re.search(r"arr:\s*ds\.w\s+4\b", body), body
