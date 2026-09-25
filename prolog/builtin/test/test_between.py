import sys

import pytest

from prolog.interpreter.test.tool import assert_true, assert_false, prolog_raises


@pytest.mark.parametrize('lower', [
    0, sys.maxint - 2, sys.maxint - 1, sys.maxint,
    -sys.maxint - 3, -sys.maxint - 2, -sys.maxint - 1,
    10 ** 50, -10 ** 50,
])
def test_between_enumeration(lower):
    upper = lower + 2
    assert_true('findall(X, between(%d, %d, X), Xs), Xs == [%d, %d, %d].'
                % (lower, upper, lower, lower + 1, upper))
    assert_true('findall(X, between(%d, %d, X), Xs), Xs == [%d].'
                % (lower, lower, lower))
    assert_false('between(%d, %d, _).' % (upper, lower))


@pytest.mark.parametrize('lower, upper', [
    (-2, 2), (-sys.maxint - 1, sys.maxint),
    (sys.maxint, sys.maxint + 2), (-sys.maxint - 3, -sys.maxint),
    (10 ** 50, 10 ** 50 + 2), (-10 ** 50, -10 ** 50 + 2),
    (-10 ** 50, 10 ** 50), (0, 10 ** 50), (-10 ** 50, 0),
])
def test_between_membership(lower, upper):
    for value in [lower, (lower + upper) // 2, upper]:
        assert_true('between(%d, %d, %d).' % (lower, upper, value))
    for value in [lower - 1, upper + 1, -10 ** 100, 10 ** 100]:
        assert_false('between(%d, %d, %d).' % (lower, upper, value))
    assert_false('between(%d, %d, %d).' % (upper, lower, lower))


def test_between_large_range_is_lazy():
    assert_true('between(0, %d, X), !, X == 0.' % (10 ** 100))
    assert_true('between(%d, 0, X), !, X == %d.'
                % (-10 ** 100, -10 ** 100))


@pytest.mark.parametrize('query, error', [
    ('between(_, 1, _)', 'instantiation_error'),
    ('between(1, _, _)', 'instantiation_error'),
    ('between(a, 1, _)', 'type_error(integer, a)'),
    ('between(0, a, _)', 'type_error(integer, a)'),
    ('between(0, 1, a)', 'type_error(integer, a)'),
    ('between(0.0, 1, _)', 'type_error(integer, 0.0)'),
    ('between(0, 1.0, _)', 'type_error(integer, 1.0)'),
    ('between(0, 1, 1.0)', 'type_error(integer, 1.0)'),
    ('between(0, 1+1, _)', 'type_error(integer, 1+1)'),
])
def test_between_errors(query, error):
    prolog_raises(error, query)
