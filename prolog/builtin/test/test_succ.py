import sys

import pytest

from prolog.interpreter.test.tool import assert_true, assert_false, prolog_raises


@pytest.mark.parametrize('predecessor', [0, 42, sys.maxint - 1, sys.maxint,
                                         sys.maxint + 1, 10 ** 50])
def test_succ_modes(predecessor):
    successor = predecessor + 1
    assert_true('succ(%d, X), X == %d.' % (predecessor, successor))
    assert_true('succ(X, %d), X == %d.' % (successor, predecessor))
    assert_true('succ(%d, %d).' % (predecessor, successor))
    assert_false('succ(%d, %d).' % (predecessor, predecessor))


def test_zero_has_no_predecessor():
    assert_false('succ(_, 0).')


@pytest.mark.parametrize('query, error', [
    ('succ(_, _)', 'instantiation_error'),
    ('succ(X, X)', 'instantiation_error'),
    ('succ(-1, _)', 'domain_error(not_less_than_zero, -1)'),
    ('succ(_, -1)', 'domain_error(not_less_than_zero, -1)'),
    ('succ(0, -1)', 'domain_error(not_less_than_zero, -1)'),
    ('succ(-100000000000000000000000, _)',
     'domain_error(not_less_than_zero, -100000000000000000000000)'),
    ('succ(_, -100000000000000000000000)',
     'domain_error(not_less_than_zero, -100000000000000000000000)'),
    ('succ(a, _)', 'type_error(integer, a)'),
    ('succ(_, a)', 'type_error(integer, a)'),
    ('succ(1.0, _)', 'type_error(integer, 1.0)'),
    ('succ(0, 1.0)', 'type_error(integer, 1.0)'),
    ('succ(1+1, _)', 'type_error(integer, 1+1)'),
])
def test_succ_errors(query, error):
    prolog_raises(error, query)
