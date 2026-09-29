import pytest
from prolog.interpreter.test.tool import assert_true, assert_false


@pytest.mark.parametrize('setup, left, right', [
    ('X = f(X)', 'X', 'X'),
    ('X = f(X), Y = f(Y)', 'X', 'Y'),
    ('X = f(X), Y = f(f(Y))', 'X', 'Y'),
    ('X = f(f(X)), Y = f(f(Y))', 'X', 'f(Y)'),
    ('X = [a|X], Y = [a,a|Y]', 'X', 'Y'),
    ('X = f(X,A), Y = f(Y,A)', 'X', 'Y'),
    ('X = f(A), Y = g(X,X)', 'Y', 'g(f(A),f(A))'),
])
def test_identical_cycles_and_sharing(setup, left, right):
    assert_true('%s, %s == %s.' % (setup, left, right))
    assert_true('%s, %s == %s.' % (setup, right, left))
    assert_false('%s, %s \\== %s.' % (setup, left, right))


@pytest.mark.parametrize('setup', [
    'X = f(X), Y = g(Y)',
    'X = f(X,a), Y = f(Y,b)',
    'X = f(X,A), Y = f(Y,B)',
    'X = f(X), Y = f(A)',
    'X = [a|X], Y = [a,b|Y]',
    'X = f(X,a), Y = f(f(Y,b),a)',
])
def test_distinct_cycles(setup):
    assert_false('%s, X == Y.' % setup)
    assert_true('%s, X \\== Y.' % setup)
    assert_true('%s, Y \\== X.' % setup)


def test_identity_does_not_bind_or_call_hooks():
    assert_true('X \\== Y, var(X), var(Y).')
    assert_true('put_attr(X, missing_hook, a), '
                'X == X, X \\== Y, X \\== a, var(X), var(Y).')
    assert_true('X = f(X,A), Y = f(Y,B), X \\== Y, var(A), var(B).')


def test_atomic_identity():
    assert_true('1 == 1, 1 \\== 1.0, 1.0 == 1.0, a == a, a \\== b, a \\== 1.')
    assert_true('100000000000000000000 == 100000000000000000000.')


def test_memo_cleanup():
    from prolog.builtin.unify import identity_state
    assert_true('X = f(X), Y = f(f(Y)), X == Y.')
    assert identity_state.seen is None
    assert_false('X = f(X,a), Y = f(Y,b), X == Y.')
    assert identity_state.seen is None
    assert_true('a == a, X \\== Y, X == X.')


@pytest.mark.parametrize('query', [
    'X == X',
    'X = Y, X == Y',
    'X = f(X), X == X',
    'put_attr(X, missing_hook, X), X == X, var(X)',
    'a == a',
    'a \\== b, \\+ (a == b)',
    'X = a, Y = a, X == Y',
    'X = a, Y = b, X \\== Y, \\+ (X == Y)',
    'X is 1 + 0, Y is 2 - 1, X == Y',
    'X is 1.5 + 0.0, Y is 3.0 / 2.0, X == Y',
    '1 \\== 1.0, 1 \\== 2, 1.5 \\== 2.5, a \\== 1',
    '100000000000000000000 == 100000000000000000000',
])
def test_identity_fast_paths_skip_traversal(monkeypatch, query):
    from prolog.builtin import unify

    def unexpected_traversal(left, right, memoized):
        pytest.fail('identity fast path entered the recursive checker')

    monkeypatch.setattr(unify, 'identity_visit', unexpected_traversal)
    assert_true(query + '.')


def test_atom_identity_of_distinct_objects(monkeypatch):
    from prolog.builtin import unify
    from prolog.interpreter.term import Atom

    def unexpected_traversal(left, right, memoized):
        pytest.fail('atom identity entered the recursive checker')

    monkeypatch.setattr(unify, 'identity_visit', unexpected_traversal)
    # Distinct instances with equivalent signatures must still compare equal.
    assert unify.identical(Atom('a'), Atom('a'))
    assert not unify.identical(Atom('a'), Atom('b'))


@pytest.mark.parametrize('kind', ['integer', 'float', 'bigint'])
def test_numeric_identity_of_distinct_objects(monkeypatch, kind):
    from prolog.builtin import unify
    from prolog.interpreter import term
    from rpython.rlib.rbigint import rbigint

    def make_number(value):
        if kind == 'integer':
            return term.Number(value)
        if kind == 'float':
            return term.Float(float(value))
        return term.BigInt(rbigint.fromint(value))

    def unexpected_traversal(left, right, memoized):
        pytest.fail('numeric identity entered the recursive checker')

    monkeypatch.setattr(unify, 'identity_visit', unexpected_traversal)
    left, right = make_number(1), make_number(1)
    assert left is not right
    assert unify.identical(left, right)
    assert not unify.identical(left, make_number(2))


def test_bigint_is_atomic():
    assert_true('atomic(100000000000000000000).')
