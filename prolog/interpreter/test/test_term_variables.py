import pytest
from prolog.interpreter.test.tool import assert_true, assert_false, prolog_raises
from prolog.interpreter.test.tool import get_engine

def test_basic_term_variables():
    assert_true("term_variables(X, [X]).")
    assert_false("term_variables(X, []).")
    assert_true("term_variables(f(X, Y), [X, Y]).")
    assert_true("term_variables(a, []).")
    assert_true("term_variables(123, []).")
    assert_true("term_variables(f(Z, g(X), Y), [Z, X, Y]).")
    assert_false("term_variables(a, a).")

def test_more_advanced_term_variables():
    assert_true("term_variables([Y,Y,X,X],[Y,X]).")
    assert_true("term_variables([X, Y, a, f(g(A), X)], [X, Y, A]).")
    assert_true("term_variables((A :- B, C, A), [A,B,C]).")
    assert_true("term_variables(f(X, f(X)), [X]).")
    assert_true("X = 1, term_variables(f(X, Y), L), L == [Y], Y = 2.")
    assert_true("X = Y, term_variables(f(X, Y), L), L == [Y], Y = 2.")

def test_var_binding():
    assert_true("X = a, term_variables(X, []).")
    assert_true("term_variables(X, L), X = a, L = [a].")
    assert_true("X = f(A,B), term_variables(X, [A,B]).")


def test_output_unification_does_not_change_collection():
    # The output may alias input variables: collect before binding any of them.
    assert_true('term_variables(f(X,Y), [Y,X]), X == Y.')
    assert_true('term_variables(f(X,X), [f(Y)]), X == f(Y), var(Y).')


def test_output_capacity():
    assert_true('term_variables(f(X,Y), [A|T]), A == X, T == [Y].')
    assert_true('T = [], term_variables(f(X,X), [A|T]), A == X.')
    assert_false('T = [], term_variables(f(X,Y), [A|T]).')
    assert_false('term_variables(f(X), [A|bad]).')
    assert_false('term_variables(f(X), [A,B]).')
    assert_false('L = [A|L], term_variables(f(X), L).')


@pytest.mark.parametrize('capacity', [0, 1])
@pytest.mark.parametrize('attributes', [False, True])
def test_short_output_stops_traversal(monkeypatch, capacity, attributes):
    from prolog.builtin.term_variables import term_variables
    from prolog.interpreter import term
    from prolog.interpreter.continuation import Heap
    from prolog.interpreter.error import UnificationFailed
    from prolog.interpreter.helper import wrap_list

    heap = Heap()
    inputs = []
    for i in range(capacity + 1):
        if attributes:
            var = heap.new_attvar()
            var.add_attribute('m', term.Callable.build('a'))
        else:
            var = heap.newvar()
        inputs.append(var)
    untouched = heap.newvar()
    original = term.BindingVar.getbinding

    def getbinding(var):
        assert var is not untouched, 'traversed beyond exhausted output capacity'
        return original(var)

    monkeypatch.setattr(term.BindingVar, 'getbinding', getbinding)
    heads = [heap.newvar() for i in range(capacity)]
    source = term.Callable.build('f', inputs + [untouched])
    with pytest.raises(UnificationFailed):
        term_variables(None, heap, source, wrap_list(heads), attributes)
    assert all(var.getbinding() is None for var in inputs + heads)


@pytest.mark.parametrize('setup, expected', [
    ('X = f(X)', '[]'),
    ('X = f(X, A)', '[A]'),
    ('X = f(A, X)', '[A]'),
    ('X = f(A, Y, B), Y = g(C, X, A)', '[A,C,B]'),
    ('X = [A,B,A|X]', '[A,B]'),
    ('Y = f(A,B), X = g(Y,C,Y,A)', '[A,B,C]'),
])
def test_cycles_and_shared_terms(setup, expected):
    assert_true('%s, term_variables(X, L), L == %s.' % (setup, expected))


def test_cycle_output_mismatch_and_backtracking():
    assert_false('X = f(X,A), term_variables(X, []).')
    assert_true('X = f(X,A), (term_variables(X, []); '
                'term_variables(X, L), L == [A]).')


def test_term_attvars_cycles_and_order():
    assert_true('X = f(X), term_attvars(X, L), L == [].')
    assert_true('put_attr(A, m, ignored), put_attr(B, m, ignored), '
                'X = f(A,Y,B), Y = g(C,X,A), '
                'term_attvars(X, L), L == [A,B], '
                'term_variables(X, V), V == [A,C,B].')


def test_numbervars_on_cycle():
    from prolog.interpreter.continuation import Engine
    assert_true("X = f(X,A,B,A), numbervars(X,0,N), N == 2, "
                "A == '$VAR'(0), B == '$VAR'(1).", Engine(load_system=True))

def test_term_variables_huge_list():
    pytest.skip("")
    e = get_engine("""
        make_triple_list(0, _, []).
        make_triple_list(X, Y, [Y, Y, Y | T]) :-
            X > 0, X1 is X - 1,
            make_triple_list(X1, Y, T).
            """)
    assert_true("make_triple_list(4000, a, L), term_variables(L, L1), L1 == [].", e)
