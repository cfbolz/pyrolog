import pytest
from prolog.interpreter.test.tool import assert_true
from prolog.interpreter.parsing import get_engine


SOURCE = '''
    restore_attributes([]).
    restore_attributes([Goal|Rest]) :- call(Goal), restore_attributes(Rest).
'''

CASES = [
    # Payload variables must be fresh, with sharing between term and goals.
    'put_attr(X,m,node(Y,Y)), copy_term(pair(X,Y),pair(C,D),G), '
    'G == [put_attr(C,m,node(D,D))], C \\== X, D \\== Y, '
    'term_attvars(pair(C,D)-G,[]), restore_attributes(G), '
    'get_attr(C,m,P), P == node(D,D), D=changed, var(Y), '
    'get_attr(X,m,O), O == node(Y,Y)',
    'put_attr(X,m,X), copy_term(X,C,G), G == [put_attr(C,m,C)], '
    'C \\== X, term_attvars(C-G,[]), restore_attributes(G), '
    'get_attr(C,m,P), P == C, get_attr(X,m,O), O == X',
    # Y is reachable only through X's attribute.
    'put_attr(X,m,peer(Y)), put_attr(Y,m,peer(X)), '
    'copy_term(X,C,G), G = [put_attr(C,m,peer(D)),put_attr(D,m,peer(C))], '
    'C \\== X, D \\== Y, term_attvars(C-G,[]), restore_attributes(G), '
    'get_attr(C,m,P), P == peer(D), get_attr(D,m,Q), Q == peer(C), '
    'get_attr(X,m,O), O == peer(Y), get_attr(Y,m,R), R == peer(X)',
    'T=f(T,Y), put_attr(X,m,T), copy_term(pair(X,Y),pair(C,D),G), '
    'G = [put_attr(C,m,P)], P == f(P,D), D \\== Y, '
    'term_attvars(pair(C,D)-G,[]), restore_attributes(G), '
    'get_attr(C,m,Q), Q == P, D=changed, var(Y)',
    # The ordinary term and an attribute can refer to each other.
    'T=f(X,T), put_attr(X,m,T), copy_term(T,C,G), '
    'C = f(D,C), G == [put_attr(D,m,C)], term_attvars(C-G,[]), '
    'restore_attributes(G), get_attr(D,m,P), P == C, D \\== X',
    'put_attr(X,m,Y), put_attr(X,n,Y), copy_term(X,C,G), '
    'G = [put_attr(C,m,D),put_attr(C,n,E)], D == E, D \\== Y, var(D)',
    'put_attr(X,m,a), put_attr(X,n,b), del_attr(X,m), '
    'copy_term(X,C,G), G == [put_attr(C,n,b)], not(attvar(C))',
    'put_attr(X,m,a), del_attrs(X), copy_term(X,C,G), G == [], not(attvar(C))',
    'freeze(X,throw(woke)), copy_term(X,C,G), not(attvar(C)), '
    'term_attvars(C-G,[]), attvar(X)',
    # A failed output match must not remove or change source attributes.
    'put_attr(X,m,X), not(copy_term(X,_,[])), get_attr(X,m,P), P == X',
]


@pytest.mark.parametrize('query', CASES)
def test_copy_attributes(query):
    assert_true(query + '.', get_engine(SOURCE, load_system=True))


def test_attribute_discovery_follows_payloads_without_binding():
    assert_true('put_attr(X,m,peer(Y)), put_attr(Y,m,peer(X)), '
                'term_attvars(X,L), L == [X,Y], '
                'term_variables(X,V), V == [X].')


def test_copy_preserves_shared_payload_compounds():
    values = assert_true('T=f(A), put_attr(X,m,T), '
                         'copy_term(pair(X,T),pair(C,U),[put_attr(C,m,V)]).')
    assert values['U'] is values['V']
    assert values['U'] is not values['T']
    assert values['U'].argument_at(0).dereference(None) is not values['A']
