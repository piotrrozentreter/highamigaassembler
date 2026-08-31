"""Tests for tools/q16_helper.py (Q16.16 fixed-point conversion)."""
import pytest

from tools.q16_helper import (
    format_q16_constant,
    q16_from_float,
    q16_from_parts,
    q16_to_float,
)


class TestFromFloat:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (0.0, 0),
            (1.0, 65536),
            (2.5, 163840),
            (0.5, 32768),
            (-1.0, -65536),
        ],
    )
    def test_known_conversions(self, value, expected):
        assert q16_from_float(value) == expected

    def test_one_over_65536_is_the_smallest_representable_step(self):
        assert q16_from_float(1.0 / 65536.0) == 1

    def test_values_below_the_step_truncate_to_zero(self):
        assert q16_from_float(1.0 / 131072.0) == 0


class TestFromParts:
    def test_integer_and_fraction_combine(self):
        # 43.55 -> (43 << 16) + (55 * 65536 // 100)
        assert q16_from_parts(43, 55) == (43 << 16) + 36044

    def test_zero_fraction_is_a_plain_shift(self):
        assert q16_from_parts(7, 0) == 7 << 16

    def test_decimal_places_scales_the_fraction(self):
        assert q16_from_parts(0, 5, decimal_places=1) == 32768
        assert q16_from_parts(0, 500, decimal_places=3) == 32768

    def test_negative_integer_part_subtracts_the_fraction(self):
        assert q16_from_parts(-2, 50) == (-2 << 16) - 32768


class TestRoundTrip:
    @pytest.mark.parametrize("value", [0.0, 0.5, 1.0, 2.5, -3.25, 100.125])
    def test_exact_binary_fractions_round_trip(self, value):
        assert q16_to_float(q16_from_float(value)) == value

    def test_to_float_divides_by_65536(self):
        assert q16_to_float(163840) == 2.5


class TestFormatting:
    def test_named_constant_uses_has_const_syntax(self):
        assert format_q16_constant(2.5, "SPEED") == "const SPEED = 163840;  // 2.5 in Q16.16"

    def test_anonymous_value_emits_the_raw_number(self):
        assert format_q16_constant(2.5) == "163840  // 2.5"
