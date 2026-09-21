import pytest
from prolog.interpreter.test.tool import assert_true, assert_false
from prolog.interpreter.continuation import Engine, Heap


@pytest.mark.parametrize('query', [
    'X = f(X), unify_with_occurs_check(Y,X), nonvar(Y).',
    'X = f(X), unify_with_occurs_check(X,X).',
    'X = f(X), Y = f(Y), unify_with_occurs_check(X,Y).',
    'X = f(X), Y = f(f(Y)), unify_with_occurs_check(X,Y).',
    'X = f(X,A), unify_with_occurs_check(Y,X), var(A).',
    'T = f(A), unify_with_occurs_check(X,g(T,T)), var(A).',
])
def test_existing_cycles_and_sharing(query):
    assert_true(query)


@pytest.mark.parametrize('query', [
    'X = f(X,Y), unify_with_occurs_check(Y,X).',
    'X = f(Y,X), unify_with_occurs_check(Y,X).',
    'X = f(Z), Z = g(X,Y), unify_with_occurs_check(Y,X).',
    'X = f(X,a), Y = f(Y,b), unify_with_occurs_check(X,Y).',
])
def test_reject_cycles_and_conflicts(query):
    assert_false(query)


def test_occurs_check_backtracking():
    assert_true('X = f(X,Y), (unify_with_occurs_check(Y,X); '
                'var(Y), unify_with_occurs_check(Y,a)), Y == a.')


def test_attributed_variable_occurs_check():
    engine = Engine(load_system=True)
    assert_true('freeze(X, W = woke), '
                '\\+ unify_with_occurs_check(X,f(X)), var(X), var(W), '
                'unify_with_occurs_check(X,a), W == woke.', engine)
    assert_true('freeze(X, W = woke), Y = f(Y), '
                'unify_with_occurs_check(X,Y), W == woke.', engine)
    assert_true('freeze(X, true), '
                '\\+ (T = f(T,X), unify_with_occurs_check(X,T)), var(X).', engine)


def test_contains_var_deep_term():
    from prolog.interpreter.term import Callable
    heap = Heap()
    needle = heap.newvar()
    other = heap.newvar()
    obj = needle
    for i in range(3000):
        obj = Callable.build('f', [obj])
    assert obj.contains_var(needle, heap)
    assert not obj.contains_var(other, heap)
