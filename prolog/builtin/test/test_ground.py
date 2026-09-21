import pytest
from prolog.interpreter.test.tool import assert_true, assert_false


@pytest.mark.parametrize('query', [
    'X = f(X), ground(X).',
    'X = f(Y), Y = g(X), ground(X).',
    'L = [a|L], ground(L).',
    'X = f(a), ground(pair(X, X)).',
])
def test_ground_cycles_and_sharing(query):
    assert_true(query)


@pytest.mark.parametrize('query', [
    'X = f(Y, X), ground(X).',
    'X = f(X, Y), ground(X).',
    'X = f(Y), Y = g(X, Z), ground(X).',
    'L = [X|L], ground(L).',
])
def test_nonground_cycles(query):
    assert_false(query)


def test_ground_large_finite_term():
    # A shallow tree exceeds the fast-path budget without relying on cycles.
    args = ','.join(['a'] * 100)
    assert_true('ground(f(%s)).' % args)
    assert_false('ground(f(%s, X)).' % args)


def test_ground_resets_budget_between_calls():
    assert_true('X = f(X), ground(X), ground(a), '
                '\\+ ground(Y), ground(X).')


def test_ground_ignores_attributes():
    assert_false('put_attr(X, m, a), ground(X).')
    assert_true('put_attr(X, m, a), ground(a).')


def test_ground_releases_memo():
    from prolog.builtin.type import ground_state
    assert_true('X = f(X), ground(X).')
    assert ground_state.seen is None
    assert_false('X = f(X, Y), ground(X).')
    assert ground_state.seen is None
