import pytest

from prolog.interpreter.parsing import get_engine
from prolog.interpreter.test.tool import assert_true
from prolog.builtin.unifiable import Unifier
from prolog.interpreter import term, error


CASES = [
    'not(unifiable(f(X,X), f(a,b), _)), var(X)',
    'not(unifiable(f(X,Y,X), f(Y,a,b), _)), var(X), var(Y)',
    'unifiable(f(X,X), f(a,a), L), L == [X-a], var(X)',
    'unifiable(f(X,Y), f(Y,a), L), L == [Y-a,X-Y], var(X), var(Y), X \\== Y',
    'unifiable(X, f(X), L), L == [X-f(X)], var(X)',
    'unifiable(f(X,Y), f(Y,f(X)), L), L == [Y-f(X),X-Y], var(X), var(Y)',
    'X = f(X), Y = f(f(Y)), unifiable(X,Y,L), L == []',
    'X = f(X,A), Y = f(f(Y,b),b), unifiable(X,Y,L), L == [A-b], var(A)',
    'X = f(X,a), Y = f(Y,b), not(unifiable(X,Y,_))',
    'X = [A|X], Y = [b,b|Y], unifiable(X,Y,L), L == [A-b], var(A)',
    'not(unifiable(X,a,[])), var(X)',
    'freeze(X, throw(woke)), unifiable(X,a,L), L == [X-a], attvar(X)',
    'freeze(X, throw(woke)), not(unifiable(f(X,X),f(a,b),_)), attvar(X)',
    'freeze(X, throw(woke)), freeze(Y, throw(woke)), '
    'unifiable(X,Y,L), L == [X-Y], attvar(X), attvar(Y), X \\== Y',
    'freeze(X, Flag=ran), unifiable(X,a,_), var(Flag), X=a, Flag == ran',
    # Returning the result is ordinary unification and may intentionally bind
    # input variables if the caller aliases them with the output pattern.
    'freeze(X, Flag=ran), unifiable(X,a,[a-a]), X == a, Flag == ran',
    'not(unifiable(1,1.0,_)), unifiable(1.0,1.0,L), L == []',
    'unifiable(10000000000000000000000,10000000000000000000000,L), L == []',
    'when(?=(f(X,X),f(a,b)), Flag=ran), Flag == ran, var(X)',
    'when(?=(f(X,Y),f(a,b)), Flag=ran), var(Flag), X=Y, Flag == ran, var(X)',
    'dif(f(X,X),f(a,b)), var(X)',
    'X=f(X), Y=f(f(Y)), not(dif(X,Y))',
    'X=f(X,A), Y=f(Y,b), dif(X,Y), not(A=b), A=c',
]


def test_unifiable_is_available_without_library():
    assert_true('unifiable(X,a,L), L == [X-a], var(X).')


@pytest.mark.parametrize('query', CASES)
def test_unifiable(query):
    assert_true(query + '.', get_engine('', load_system=True))


def test_dictionary_unification_never_binds_inputs_even_on_failure():
    x = term.BindingVar()
    left = term.Callable.build('f', [x,x])
    right = term.Callable.build('f', [term.Callable.build('a'),term.Callable.build('b')])
    with pytest.raises(error.UnificationFailed):
        Unifier().unify(left, right)
    assert x.getbinding() is None


def test_shared_graphs_and_deep_terms():
    x, y = term.BindingVar(), term.BindingVar()
    left, right = x, y
    for i in range(2000):
        left = term.Callable.build('f', [left,left])
        right = term.Callable.build('f', [right,right])
    unifier = Unifier()
    unifier.unify(left,right)
    assert len(unifier.seen) == 2000
    assert len(unifier.bindings) == 1
    assert unifier.substitutions[x] is y
    assert x.getbinding() is None and y.getbinding() is None


@pytest.mark.parametrize('left, right', [
    ('f(X,Y)', 'f(Y,a)'),
    ('f(X,X)', 'f(Y,Z)'),
    ('f(X,Y)', 'f(Y,f(X))'),
    ('A', 'B'),
    ('L', '[a,a|L]'),
    ('f(A,X)', 'f(B,b)'),
])
def test_returned_equations_actually_unify_inputs(left, right):
    engine = get_engine('''
        apply_bindings([]).
        apply_bindings([X-Y|Rest]) :- X=Y, apply_bindings(Rest).
    ''', load_system=True)
    assert_true('A = f(A,X), B = f(f(B,Y),Y), L = [X|L], '
                'unifiable(%s,%s,Bindings), apply_bindings(Bindings), '
                '%s == %s.' % (left, right, left, right), engine)
