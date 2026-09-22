"""Check numeric boundaries against independent Python arithmetic."""
import operator
import sys
import math

from hypothesis import given, strategies as st, settings, example
from rpython.rlib.rbigint import rbigint

from prolog.builtin import arithmeticbuiltin
from prolog.interpreter import arithmetic, error, term


def wrap_number(value, force_bigint=False):
    if isinstance(value, float):
        return term.Float(value)
    if not force_bigint and -sys.maxint - 1 <= value <= sys.maxint:
        return term.Number(int(value))
    return term.BigInt(rbigint.fromdecimalstr(str(value)))


def unwrap_integer(value):
    if isinstance(value, term.Number):
        return value.num
    assert isinstance(value, term.BigInt)
    return long(value.value.str())


integers = st.integers(-(2 ** 1024), 2 ** 1024)
numbers = st.one_of(integers, st.floats())


@settings(max_examples=200, deadline=None)
@given(st.floats(allow_nan=False, allow_infinity=False),
       st.floats(allow_nan=False, allow_infinity=False))
@example(1.0e308, 2.0)
@example(sys.float_info.max, sys.float_info.max)
@example(1.0, 1.0e-320)
@example(-0.0, 2.0)
@example(1.0e-320, 2.0)
def test_float_operations(left, right):
    lhs, rhs = term.Float(left), term.Float(right)
    for name in ['add', 'sub', 'mul', 'div']:
        expected_error = None
        if name == 'div' and right == 0.0:
            expected_error = 'zero_divisor'
        else:
            operation = operator.truediv if name == 'div' else getattr(operator, name)
            expected = operation(left, right)
            if math.isinf(expected):
                expected_error = 'float_overflow'
        try:
            actual = getattr(lhs, 'arith_' + name)(rhs)
        except error.CatchableError as exc:
            assert expected_error is not None
            err = exc.term.argument_at(0)
            assert err.name() == 'evaluation_error'
            assert err.argument_at(0).name() == expected_error
        else:
            assert expected_error is None
            assert actual.floatval == expected
            if expected == 0.0:
                assert math.copysign(1.0, actual.floatval) == math.copysign(1.0, expected)


@settings(max_examples=200, deadline=None)
@given(numbers, numbers, st.booleans(), st.booleans())
@example(2 ** 53 + 1, float(2 ** 53), False, False)
@example(-(2 ** 53 + 1), -float(2 ** 53), False, False)
@example(0, -0.5, True, False)
@example(0, 0.5, True, False)
@example(0, -0.0, True, False)
@example(10 ** 400, float('inf'), False, False)
@example(float('nan'), 1, False, False)
def test_numeric_comparisons(left, right, left_big, right_big):
    lhs = wrap_number(left, left_big)
    rhs = wrap_number(right, right_big)
    for name in ['eq', 'ne', 'lt', 'le', 'gt', 'ge']:
        expected = getattr(operator, name)(left, right)
        predicate = getattr(arithmeticbuiltin, 'impl_arith_' + name)
        try:
            predicate(None, None, lhs, rhs)
        except error.UnificationFailed:
            actual = False
        else:
            actual = True
        assert actual == expected


@settings(max_examples=100, deadline=None)
@given(integers, integers, st.booleans(), st.booleans())
def test_exact_integer_operations(left, right, left_big, right_big):
    lhs = wrap_number(left, left_big)
    rhs = wrap_number(right, right_big)
    for name in ['add', 'sub', 'mul']:
        actual = getattr(lhs, 'arith_' + name)(rhs)
        assert unwrap_integer(actual) == getattr(operator, name)(left, right)
    assert unwrap_integer(lhs.arith_and(rhs)) == left & right
    assert unwrap_integer(lhs.arith_or(rhs)) == left | right
    assert unwrap_integer(lhs.arith_xor(rhs)) == left ^ right
    assert unwrap_integer(lhs.arith_not()) == ~left
    if right:
        assert unwrap_integer(lhs.arith_mod(rhs)) == left % right


@settings(max_examples=100, deadline=None)
@given(integers, st.integers(0, 2048), st.booleans(), st.booleans())
@example(1, 64, False, False)
@example(-1, 64, False, False)
def test_integer_shifts(value, count, value_big, count_big):
    lhs = wrap_number(value, value_big)
    rhs = wrap_number(count, count_big)
    assert unwrap_integer(lhs.arith_shl(rhs)) == value << count
    assert unwrap_integer(lhs.arith_shr(rhs)) == value >> count


@settings(max_examples=100, deadline=None)
@given(st.integers(-(2 ** 64), 2 ** 64), st.integers(0, 100),
       st.booleans(), st.booleans())
@example(3, 34, False, False)
def test_integer_powers(base, exponent, base_big, exponent_big):
    lhs = wrap_number(base, base_big)
    rhs = wrap_number(exponent, exponent_big)
    assert unwrap_integer(lhs.arith_pow(rhs)) == base ** exponent


@settings(max_examples=100, deadline=None)
@given(st.floats(allow_nan=False, allow_infinity=False))
def test_round_float(value):
    # Exact rational arithmetic gives rounding with ties away from zero.
    numerator, denominator = value.as_integer_ratio()
    expected = (2 * abs(numerator) + denominator) // (2 * denominator)
    if numerator < 0:
        expected = -expected
    assert unwrap_integer(term.Float(value).arith_round()) == expected
