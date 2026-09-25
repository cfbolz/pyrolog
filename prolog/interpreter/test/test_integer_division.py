import sys

import pytest
from rpython.rlib.rbigint import rbigint

from prolog.interpreter import error, term
from prolog.interpreter.test.tool import assert_true, prolog_raises


@pytest.mark.parametrize('left, right, quotient, remainder', [
    (5, 2, 2, 1), (-5, 2, -3, -1), (5, -2, -3, 1), (-5, -2, 2, -1),
    (-1, 2, -1, -1), (1, -2, -1, 1), (-6, 2, -3, 0), (0, -2, 0, 0),
    (-10 ** 20 - 1, 3, -33333333333333333334, -2),
    (10 ** 20 + 1, -3, -33333333333333333334, 2),
    (-5, 10 ** 20, -1, -5), (5, -10 ** 20, -1, 5),
    (-10 ** 20 - 1, 10 ** 20, -2, -1),
    (-sys.maxint - 1, -1, sys.maxint + 1, 0),
])
def test_div_and_rem(left, right, quotient, remainder):
    assert_true('Q is (%d) div (%d), Q == %d, '
                'R is (%d) rem (%d), R == %d.' %
                (left, right, quotient, left, right, remainder))


def test_div_operator_precedence_and_associativity():
    assert_true('X is 20 div 3 div 2, X == 3.')
    assert_true('X is 1 + 20 div 3 * 2, X == 13.')
    assert_true('X is div(-5, 2), X == -3.')
    assert_true('X is rem(-5, 2), X == -1.')


@pytest.mark.parametrize('operator', ['div', 'rem'])
@pytest.mark.parametrize('numerator', [1, 10 ** 100])
def test_zero_divisor(operator, numerator):
    prolog_raises('evaluation_error(zero_divisor)',
                  'X is %d %s 0' % (numerator, operator))


@pytest.mark.parametrize('operator', ['div', 'rem'])
@pytest.mark.parametrize('left, right, culprit', [
    ('1.0', '2', '1.0'), ('1', '2.0', '2.0'),
    ('1.0', str(10 ** 100), '1.0'), (str(10 ** 100), '2.0', '2.0'),
    ('1.0', '2.0', '1.0'), ('1.0', '0', '1.0'),
])
def test_requires_integers(operator, left, right, culprit):
    prolog_raises('type_error(integer, %s)' % culprit,
                  'X is %s %s %s' % (left, operator, right))


@pytest.mark.parametrize('operator', ['div', 'rem'])
def test_evaluates_operands(operator):
    prolog_raises('instantiation_error', 'X is Y %s 2' % operator)
    prolog_raises('type_error(evaluable, a/0)', 'X is a %s 2' % operator)
    assert_true('X is (3 + 2) %s (1 + 1), integer(X).' % operator)


@pytest.mark.parametrize('method', ['arith_func_div', 'arith_rem'])
@pytest.mark.parametrize('big_numerator', [False, True])
def test_bigint_zero_divisor(method, big_numerator):
    numerator = term.Number(1)
    if big_numerator:
        numerator = term.BigInt(rbigint.fromint(1))
    with pytest.raises(error.CatchableError):
        getattr(numerator, method)(term.BigInt(rbigint.fromint(0)))
