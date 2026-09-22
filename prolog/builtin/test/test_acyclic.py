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
    'X = f(X), copy_term(X,C), acyclic_term(C).',
    'T = f(a), X = f(T,T,X), copy_term(X,C), acyclic_term(C).',
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


@pytest.mark.parametrize('ground', [False, True])
def test_copied_shared_graph_has_linear_traversal(monkeypatch, ground):
    from prolog.builtin import type as type_builtin
    from prolog.interpreter import term
    from prolog.interpreter.continuation import Heap
    from prolog.interpreter.memo import CopyMemo

    heap = Heap()
    root = term.Callable.build('a') if ground else heap.newvar()
    depth = 24
    for i in range(depth):
        parent = term.Callable.build('f', [root, root])
        root = heap.newvar()
        root.setvalue(parent, heap)
    copied = root.copy(heap, CopyMemo())

    original = type_builtin.acyclic_visit
    visits = [0]

    def counted(obj, memoized):
        visits[0] += 1
        assert visits[0] <= type_builtin.ACYCLIC_BUDGET + 2 * depth + 2
        return original(obj, memoized)

    monkeypatch.setattr(type_builtin, 'acyclic_visit', counted)
    type_builtin.impl_acyclic_term(None, heap, copied)
    assert type_builtin.acyclic_state.seen is None
