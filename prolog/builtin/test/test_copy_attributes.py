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


PROJECTION_SOURCE = '''
    :- module(projected, []).
    attribute_goals(X) -->
        { get_attr(X, projected, Value) },
        [projected:restore(X, Value)].
    restore(X, Value) :- put_attr(X, projected, Value).
    attr_unify_hook(_, _).
'''


@pytest.mark.parametrize('query', [
    'put_attr(X,projected,pair(Y,Y)), '
    'copy_term(pair(X,Y),pair(C,D),G), '
    'G == [projected:restore(C,pair(D,D))], '
    'C \\== X, D \\== Y, term_attvars(C-D-G,[]), '
    'restore_attributes(G), get_attr(C,projected,pair(D,D)), '
    'get_attr(X,projected,pair(Y,Y))',
    'put_attr(X,projected,peer(Y)), put_attr(Y,projected,peer(X)), '
    'copy_term(X,C,G), G = [projected:restore(C,peer(D)), '
    'projected:restore(D,peer(C))], term_attvars(C-G,[]), C \\== X, D \\== Y',
    'put_attr(X,projected,Y), put_attr(X,missing_module,Y), '
    'copy_term(X,C,G), G = [projected:restore(C,D),put_attr(C,missing_module,D)], '
    'D \\== Y, term_attvars(C-G,[])',
    'T=f(X,T), put_attr(X,projected,T), copy_term(T,C,G), '
    'C=f(D,C), G == [projected:restore(D,C)], term_attvars(C-G,[])',
    'put_attr(X,projected,a), \\+ copy_term(X,_,[]), get_attr(X,projected,a)',
])
def test_attribute_goals_projection(query):
    engine = get_engine(SOURCE, load_system=True, projected=PROJECTION_SOURCE)
    assert_true(query + '.', engine)


@pytest.mark.parametrize('hook, expected', [
    ('attribute_goals(_) --> [].', '[]'),
    ('attribute_goals(X) --> [one(X), two(X)].', '[one(C),two(C)]'),
    ('attribute_goals(X) --> [first(X)]. '
     'attribute_goals(X) --> [second(X)].', '[first(C)]'),
    ('attribute_goals(_) --> { fail }.', '[put_attr(C,projected,a)]'),
])
def test_attribute_goals_results(hook, expected):
    engine = get_engine('', load_system=True,
                        projected=':- module(projected, []).\n' + hook)
    assert_true('put_attr(X,projected,a), '
                'findall(C-G,copy_term(X,C,G),[C-G]), '
                'G == %s, get_attr(X,projected,a).' % expected, engine)


@pytest.mark.parametrize('ending', ['true', 'fail', 'throw(projection_error)'])
def test_attribute_goals_restore_changes(ending):
    engine = get_engine('', load_system=True, projected='''
        :- module(projected, []).
        attribute_goals(X) -->
            { get_attr(X,projected,Y), del_attr(X,projected),
              Y=changed, %s },
            [saved(X,Y)].
    ''' % ending)
    if ending == 'true':
        result = 'copy_term(X,C,G), G == [saved(C,changed)]'
    elif ending == 'fail':
        result = 'copy_term(X,C,G), G = [put_attr(C,projected,D)], var(D)'
    else:
        result = 'catch(copy_term(X,_,_),projection_error,true)'
    assert_true('put_attr(X,projected,Y), %s, var(Y), '
                'get_attr(X,projected,V), V == Y.' % result, engine)


def test_attribute_goals_can_bind_source_temporarily():
    engine = get_engine('', load_system=True, projected='''
        :- module(projected, []).
        attribute_goals(X) --> { del_attrs(X), X=bound }, [].
    ''')
    assert_true('put_attr(X,projected,a), put_attr(X,other,b), '
                'copy_term(X,C,G), C == bound, G == [], var(X), '
                'get_attr(X,projected,a), get_attr(X,other,b).', engine)


def test_attribute_goals_can_suppress_related_variable_projection():
    engine = get_engine('', load_system=True, projected='''
        :- module(projected, []).
        attribute_goals(X) -->
            { get_attr(X,projected,Y), del_attr(Y,projected) },
            [related(X,Y)].
    ''')
    assert_true('put_attr(X,projected,Y), put_attr(Y,projected,X), '
                'copy_term(pair(X,Y),pair(C,D),G), G == [related(C,D)], '
                'get_attr(X,projected,P), P == Y, '
                'get_attr(Y,projected,Q), Q == X.', engine)


def test_attribute_goals_strip_fresh_attributes_in_emitted_goals():
    engine = get_engine('', load_system=True, projected='''
        :- module(projected, []).
        attribute_goals(X) --> { put_attr(Y,internal,a) }, [related(X,Y,Y)].
    ''')
    assert_true('put_attr(X,projected,a), copy_term(X,C,G), '
                'G = [related(C,D,E)], D == E, term_attvars(C-G,[]), '
                'get_attr(X,projected,a).', engine)
