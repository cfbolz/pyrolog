from prolog.interpreter.test.tool import assert_true, assert_false
from prolog.interpreter.parsing import get_engine
import pytest


CASES = [
    'X=f(X), Y=f(f(Y)), ?=(X,Y)',
    'X=f(X,a), Y=f(Y,b), ?=(X,Y)',
    'X=f(X,A), Y=f(Y,b), not(?=(X,Y)), var(A)',
    'X=f(X,A), Y=f(f(Y,A),A), ?=(X,Y), var(A)',
    '?=(f(X,X),f(a,b)), var(X)',
    '?=(f(X,Y,X),f(Y,a,b)), var(X), var(Y), X \\== Y',
    'not(?=(X,f(X))), var(X)',
    'not(?=(f(X,Y),f(Y,f(X)))), var(X), var(Y), X \\== Y',
    'freeze(X,throw(woke)), ?=(X,X), attvar(X)',
    'freeze(X,throw(woke)), not(?=(X,a)), attvar(X)',
    'freeze(X,throw(woke)), ?=(f(X,X),f(a,b)), attvar(X)',
    'freeze(X,throw(woke)), freeze(Y,throw(woke)), '
    'not(?=(X,Y)), attvar(X), attvar(Y), X \\== Y',
    'freeze(X,Flag=ran), not(?=(X,a)), var(Flag), X=a, Flag == ran',
    '?=(1,1.0), ?=(10000000000000000000000,10000000000000000000000)',
]


@pytest.mark.parametrize('query', CASES)
def test_rational_trees_and_attribute_isolation(query):
    assert_true(query + '.', get_engine('', load_system=True))

# sionu ~=~ structural identical or not unifiable
def test_basic_sionu():
    e = get_engine('', load_system=True)
    assert_false("?=(X, Y).", e)
    assert_true("?=(X, X).", e)
    assert_true("?=(1, 1).", e)
    assert_true("?=(1, 2).", e)
    assert_false("?=(X, 1).", e)
    assert_false("?=([X, Y], [X, X]).", e)
    assert_true("?=([X, Y], [X, Y]).", e)

def test_binding():
    e = get_engine('', load_system=True)
    assert_false("?=(X, 1), X == 1.", e)
    assert_true("(\+ ?=(X, 1)), var(X).", e)
