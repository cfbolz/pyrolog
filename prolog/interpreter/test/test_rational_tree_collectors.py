"""Rational-tree regressions for consumers of copying and variable traversal."""
import pytest

from prolog.interpreter.parsing import get_engine
from prolog.interpreter.test.tool import assert_true
from prolog.interpreter import term


FINDALL_CASES = [
    # Distinct cyclic answers survive backtracking; the template is restored.
    'findall(X, (X=f(X); X=g(X)), [F,G]), '
    'F == f(F), G == g(G), var(X)',
    # Free variables retain sharing within each answer, but not across answers
    # or with the source template.
    'T = f(T,A,A), findall(T, (true;true), [C,D]), '
    'C = f(C,B,B), D = f(D,E,E), '
    'var(A), var(B), var(E), A \\== B, B \\== E, A \\== E, '
    'B = one, var(A), var(E)',
    'T = f(T,A), findall(T, (A=a; A=b), [C,D]), '
    'C == f(C,a), D == f(D,b), var(A)',
    'X = f(X), findall(X, fail, L), L == [], X == f(X)',
    'findall(L, findall(X, (X=f(X); X=g(X)), L), [[F,G]]), '
    'F == f(F), G == g(G), var(X), var(L)',
    # A cyclic exception escapes collection without retaining goal bindings.
    'catch(findall(X, (X=f(X), throw(X)), Bag), C, true), '
    'C == f(C), var(X), var(Bag)',
]

NUMBERVARS_CASES = [
    'X = f(X), numbervars(X, 7, End), End == 7, X == f(X)',
    "X = f(X,A,B,A), numbervars(X, 7, End), End == 9, "
    "A == '$VAR'(7), B == '$VAR'(8), X == f(X,A,B,A)",
    "X = f(Y,A), Y = g(X,B,A), numbervars(X, 3, End), End == 5, "
    "B == '$VAR'(3), A == '$VAR'(4), Y == g(X,B,A)",
    "L = [A,B,A|L], numbervars(L, 0, End), End == 2, "
    "A == '$VAR'(0), B == '$VAR'(1)",
    # Failed output unification must undo numbering.
    'X = f(X,A), not(numbervars(X, 0, 2)), var(A), X == f(X,A)',
]

VARIANT_CASES = [
    'X = f(X), Y = f(f(Y)), X =@= Y',
    'X = f(X,A,A), Y = f(Y,B,B), X =@= Y, '
    'var(A), var(B), A \\== B',
    'X = f(X,A), Y = f(f(Y,B),B), X =@= Y, var(A), var(B)',
    'X = [A|X], Y = [B,B|Y], X =@= Y, var(A), var(B)',
    'X = f(X,A,A), Y = f(Y,B,C), not(X =@= Y), '
    'var(A), var(B), var(C), B \\== C',
    'X = f(X,A,B), Y = f(Y,C,C), not(X =@= Y), '
    'var(A), var(B), var(C), A \\== B',
    'X = f(X,a), Y = f(Y,b), not(X =@= Y)',
    'X = f(X), Y = g(Y), not(X =@= Y)',
]


@pytest.mark.parametrize('query', FINDALL_CASES)
def test_findall_rational_trees(query):
    assert_true(query + '.')


@pytest.mark.parametrize('query', NUMBERVARS_CASES)
def test_numbervars_rational_trees(query):
    assert_true(query + '.', get_engine('', load_system=True))


@pytest.mark.parametrize('query', VARIANT_CASES)
def test_variant_rational_trees(query):
    assert_true(query + '.', get_engine('', load_system=True))


def test_findall_preserves_compound_sharing():
    engine = get_engine('''
        dag(0, Leaf, Leaf).
        dag(N, Leaf, f(T,T)) :- N > 0, M is N-1, dag(M, Leaf, T).
    ''')
    values = assert_true('dag(24, A, T), findall(T, (true;true), [C,D]).', engine)
    left, right = values['C'], values['D']
    for i in range(24):
        assert left is not right
        left_child = left.argument_at(0).dereference(None)
        right_child = right.argument_at(0).dereference(None)
        assert left_child is left.argument_at(1).dereference(None)
        assert right_child is right.argument_at(1).dereference(None)
        left, right = left_child, right_child
    assert isinstance(left, term.Var) and left.getbinding() is None
    assert isinstance(right, term.Var) and right.getbinding() is None
    assert left is not right
    assert left is not values['A'] and right is not values['A']
