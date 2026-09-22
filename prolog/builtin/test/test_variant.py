import pytest

from prolog.builtin.unify import variant
from prolog.interpreter import term
from prolog.interpreter.test.tool import assert_true


CASES = [
    'X =@= Y, var(X), var(Y), X \\== Y',
    'X =@= X, f(X,X) =@= f(Y,Y), var(X), var(Y)',
    'not(f(X,X) =@= f(Y,Z)), var(X), var(Y), var(Z)',
    'not(f(X,Y) =@= f(Z,Z)), var(X), var(Y), var(Z)',
    'f(X,Y) =@= f(Y,X), var(X), var(Y), X \\== Y',
    # Pointer equality must still establish the variable correspondence.
    'not(f(X,X) =@= f(X,Y)), var(X), var(Y)',
    'not(f(X,Y) =@= f(X,X)), var(X), var(Y)',
    'T=g(X), not(f(T,X) =@= f(T,Y)), var(X), var(Y)',
    'T=g(X), not(f(X,T) =@= f(Y,T)), var(X), var(Y)',
    # Different finite representations of equivalent rational trees.
    'X=f(Y,A), Y=f(X,B), U=f(V,C), V=f(W,D), W=f(V,C), '
    'X =@= U, U =@= X, var(A), var(B), var(C), var(D)',
    'X=f(f(f(X,A),A),A), Y=f(Y,B), X =@= Y, Y =@= X, A \\== B',
    'X=f(X,A,A), Y=f(Y,B,C), not(X =@= Y), not(Y =@= X)',
    'X=f(X,a), Y=f(Y,b), not(X =@= Y)',
    "not(X =@= '$VAR'(0)), var(X)",
    "not(f(X,'$VAR'(0)) =@= f('$VAR'(0),Y)), var(X), var(Y)",
    'a =@= a, not(a =@= b), not(f(a) =@= g(a)), not(f(a) =@= f(a,b))',
    '1 =@= 1, 1.0 =@= 1.0, not(1 =@= 1.0), not(1 =@= a), not(a =@= 1)',
    '100000000000000000000 =@= 100000000000000000000',
    # Attributes are compared as data, without invoking module hooks.
    'put_attr(X,m,a), put_attr(Y,m,a), X =@= Y, X \\== Y, attvar(X), attvar(Y)',
    'put_attr(X,m,a), put_attr(Y,m,b), not(X =@= Y)',
    'put_attr(X,m,a), put_attr(Y,n,a), not(X =@= Y)',
    'put_attr(X,m,a), not(X =@= Y), not(Y =@= X), var(Y)',
    'put_attr(X,m,a), put_attr(Y,m,a), put_attr(Y,n,b), '
    'not(X =@= Y), not(Y =@= X)',
    # Unlike SWI's attribute chains, our maps are compared independently of
    # insertion order.
    'put_attr(X,m,A), put_attr(X,n,A), put_attr(Y,n,B), put_attr(Y,m,B), '
    'X =@= Y, var(A), var(B), A \\== B',
    'put_attr(X,m,A), put_attr(Y,m,B), pair(X,A) =@= pair(Y,B), '
    'not(pair(X,A) =@= pair(Y,C)), var(A), var(B), var(C)',
    'put_attr(X,m,A), put_attr(X,n,A), put_attr(Y,m,B), put_attr(Y,n,C), '
    'not(X =@= Y), not(Y =@= X)',
    'put_attr(X,m,X), put_attr(Y,m,Y), X =@= Y, '
    'get_attr(X,m,P), P==X, get_attr(Y,m,Q), Q==Y',
    'put_attr(X,m,Z), put_attr(Z,m,X), put_attr(Y,m,Y), not(X =@= Y)',
    'put_attr(X,m,peer(Z)), put_attr(Z,m,peer(X)), '
    'put_attr(Y,m,peer(W)), put_attr(W,m,peer(Y)), X =@= Y, Z \\== W',
    'T=f(T,A), U=f(f(U,B),B), put_attr(X,m,T), put_attr(Y,m,U), '
    'pair(X,A) =@= pair(Y,B), var(A), var(B)',
    'T=f(X,T), U=f(Y,U), put_attr(X,m,T), put_attr(Y,m,U), T =@= U',
    'put_attr(X,m,a), del_attr(X,m), X =@= Y, not(attvar(X)), var(Y)',
    'put_attr(X,m,a), del_attrs(X), X =@= Y, not(attvar(X)), var(Y)',
    'put_attr(X,m,a), put_attr(X,n,b), del_attr(X,m), '
    'put_attr(Y,n,b), X =@= Y, get_attr(X,n,b)',
]


@pytest.mark.parametrize('query', CASES)
def test_variant(query):
    # No Prolog library is needed for the builtin.
    assert_true(query + '.')


def test_deep_shared_graphs(monkeypatch):
    x, y = term.BindingVar(), term.BindingVar()
    left, right = x, y
    depth = 2000
    for i in range(depth):
        left = term.Callable.build('f', [left, left])
        right = term.Callable.build('f', [right, right])

    cls = type(left)
    original = cls.argument_at
    visits = [0]

    def counted(obj, i):
        visits[0] += 1
        assert visits[0] <= 4 * depth, 'variant traversal expanded shared paths'
        return original(obj, i)

    monkeypatch.setattr(cls, 'argument_at', counted)
    assert variant(left, right)
    assert x.getbinding() is None and y.getbinding() is None


def test_early_functor_mismatch_does_not_visit_children(monkeypatch):
    left = term.Callable.build('f', [term.BindingVar()])
    right = term.Callable.build('g', [term.BindingVar()])

    def untouched(obj, i):
        raise AssertionError('traversed arguments after a functor mismatch')

    monkeypatch.setattr(type(left), 'argument_at', untouched)
    assert not variant(left, right)
