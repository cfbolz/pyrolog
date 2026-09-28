"""Rule operations: execution must preserve sharing across calls and retries."""
from prolog.interpreter.parsing import get_engine
from prolog.interpreter.function import Rule
from prolog.interpreter.test.tool import assert_true, assert_false, collect_all


def test_conjunction_does_not_clone_whole_body(monkeypatch):
    e = get_engine('p(X) :- X = a, X == a.')
    def forbidden(*args):
        raise AssertionError('whole rule body copied')
    monkeypatch.setattr(Rule, 'clone_body_from_rulecont', forbidden)
    assert_true('p(a).', e)


def test_body_locals_survive_backtracking():
    e = get_engine('''
        choice(a). choice(b).
        p(Y) :- choice(X), X = Y, Y == X.
        q(Y) :- choice(I), choice(X), X = Y, I == b.
    ''')
    assert [r['Y'].name() for r in collect_all(e, 'p(Y).')] == ['a', 'b']
    assert [r['Y'].name() for r in collect_all(e, 'q(Y).')] == ['a', 'b']


def test_fresh_invocations_and_nested_conjunctions():
    e = get_engine('p(X) :- (X = f(Y), Y = a), X == f(a).')
    assert_true('p(X), p(Y), X == Y.', e)
    assert_false('p(f(b)).', e)


def test_existing_control_calls_inside_conjunction():
    e = get_engine('''
        p(X) :- (X = a ; X = b), X == b.
        q(X) :- p(X), !, X == b.
        q(c).
        r(X) :- catch(throw(ball), ball, X = caught), X == caught.
    ''')
    assert [r['X'].name() for r in collect_all(e, 'q(X).')] == ['b']
    assert_true('r(caught).', e)
