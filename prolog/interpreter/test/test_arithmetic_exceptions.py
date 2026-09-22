"""Regressions for host exceptions escaping arithmetic evaluation.

Invalid shifts must raise a catchable Prolog error. Valid comparisons and
large right shifts must return their result rather than raise any error.
"""
import pytest

from prolog.interpreter.test.tool import assert_true, prolog_raises


BIG = 2 ** 100


@pytest.mark.parametrize('operator', ['<<', '>>'])
@pytest.mark.parametrize('value', [1, BIG])
@pytest.mark.parametrize('count', [-1, -BIG])
def test_negative_shift_error_is_catchable(operator, value, count):
    prolog_raises('domain_error(not_less_than_zero, %s)' % count,
                  'X is %s %s (%s)' % (value, operator, count))


@pytest.mark.parametrize('value', [1, BIG])
def test_oversized_left_shift_error_is_catchable(value):
    # The count cannot fit in a machine integer; do not attempt allocation.
    prolog_raises('representation_error(shift_count)',
                  'X is %s << %s' % (value, BIG))


@pytest.mark.parametrize('value', [1, -1, BIG, -BIG])
def test_oversized_right_shift_returns_sign(value):
    expected = -1 if value < 0 else 0
    assert_true('X is (%s) >> %s, X = %s.' % (value, BIG, expected))


@pytest.mark.parametrize('operator', ['+', '-', '*', '/', 'max', 'min'])
@pytest.mark.parametrize('bigint_first', [False, True])
def test_mixed_float_bigint_overflow_is_catchable(operator, bigint_first):
    operands = [str(10 ** 400), '1.0']
    if not bigint_first:
        operands.reverse()
    left, right = operands
    if operator in ['max', 'min']:
        expression = '%s(%s, %s)' % (operator, left, right)
    else:
        expression = '%s %s %s' % (left, operator, right)
    prolog_raises('evaluation_error(float_overflow)', 'X is %s' % expression)


@pytest.mark.parametrize('operator', ['=:=', '=\\=', '<', '=<', '>', '>='])
@pytest.mark.parametrize('left,right', [
    (BIG, 1), (1, BIG), (BIG, 1.0), (1.0, BIG),
    (BIG, BIG), (BIG, BIG + 1),
])
def test_bigint_comparison_does_not_raise(operator, left, right):
    expected = {
        '=:=': left == right,
        '=\\=': left != right,
        '<': left < right,
        '=<': left <= right,
        '>': left > right,
        '>=': left >= right,
    }[operator]
    assert_true('((%s %s %s) -> R = yes; R = no), R = %s.' %
                (left, operator, right, 'yes' if expected else 'no'))


@pytest.mark.parametrize('operator', ['<<', '>>'])
@pytest.mark.parametrize('left,right', [('1.0', '2'), ('1', '2.0')])
def test_shift_requires_integer_operands(operator, left, right):
    culprit = left if left == '1.0' else right
    prolog_raises('type_error(integer, %s)' % culprit,
                  'X is %s %s %s' % (left, operator, right))
