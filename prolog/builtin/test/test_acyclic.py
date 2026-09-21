import pytest
from prolog.interpreter.test.tool import assert_true, assert_false


@pytest.mark.parametrize('query', [
    'acyclic_term(X), var(X).',
    'acyclic_term(a).',
    'acyclic_term(42).',
    'acyclic_term(f(X, X)), var(X).',
    'acyclic_term([a,b|Tail]), var(Tail).',
    'X = f(a), acyclic_term(pair(X,X)).',
    'X = Y, Y = f(Z), acyclic_term(pair(X,Y)), var(Z).',
    'put_attr(X,m,X), acyclic_term(X), var(X).',
])
def test_acyclic_terms(query):
    assert_true(query)


@pytest.mark.parametrize('query', [
    'X = f(X), acyclic_term(X).',
    'X = f(Y), Y = g(X), acyclic_term(X).',
    'X = [a|X], acyclic_term(X).',
    'X = f(X,Y), acyclic_term(X).',
    'X = f(Y,X), acyclic_term(X).',
    'X = f(X), acyclic_term(g(a,X)).',
])
def test_cyclic_terms(query):
    assert_false(query)


def test_shared_subterms_on_memoized_path():
    # Only a small graph, but exponentially many paths through it. Revisited
    # finished variables must be skipped, not treated as cycles.
    goals = ['X0 = f(A)']
    goals += ['X%d = f(X%d,X%d)' % (i, i-1, i-1) for i in range(1, 21)]
    goals += ['acyclic_term(X20)', 'var(A)']
    assert_true(', '.join(goals) + '.')


def test_memo_cleanup_and_repeated_calls():
    from prolog.builtin.type import acyclic_state
    args = ','.join(['a'] * 100)
    assert_true('acyclic_term(f(%s)).' % args)
    assert acyclic_state.seen is None
    assert_false('X = f(X), acyclic_term(X).')
    assert acyclic_state.seen is None
    assert_true('(X = f(X), acyclic_term(X); var(X)), '
                'acyclic_term(f(X)), var(X).')
