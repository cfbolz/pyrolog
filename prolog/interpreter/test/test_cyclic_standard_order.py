import pytest
from prolog.interpreter.test.tool import assert_true


CASES = []
for goal in ['L @< R', 'L @=< R', 'L @> R', 'L @>= R',
             'compare(Order,L,R)']:
    for setup, culprit in [
        ('L=f(L), R=L', 'L'),
        ('L=f(L), R=f(R)', 'L'),
        ('L=f(L), R=a', 'L'),
        ('L=a, R=f(R)', 'R'),
        ('L=f(a), R=g(R)', 'R'),
        ('L=f(a,X), X=f(X), R=f(b,z)', 'L'),
        ('L=s(R,0), R=s(L,1)', 'L'),
        ('L=[a|L], R=[]', 'L'),
    ]:
        CASES.append('%s, catch((%s, fail), '
                     'error(domain_error(cyclic_term,Culprit)), '
                     'Caught=yes), Caught==yes, Culprit==%s, var(Order)' %
                     (setup, goal, culprit))

CASES += [
    'X=f(A), compare(=,pair(X,X),pair(f(A),f(A))), var(A)',
    'put_attr(X,m,X), compare(=,X,X), var(X), get_attr(X,m,V), V==X',
    'X=f(X), X==X, X =@= X',
    'X=f(X), catch(compare(_,X,a),error(domain_error(cyclic_term,_)),true), '
    'compare(<,f(a),f(b))',
]

# Copying removes bound-variable edges while retaining compound sharing.
_shared_goals = ['X0=f(A)']
_shared_goals += ['X%d=f(X%d,X%d)' % (i, i-1, i-1) for i in range(1, 25)]
_shared_goals += ['copy_term(X24,C)', 'compare(>,C,a)', 'var(A)']
CASES.append(', '.join(_shared_goals))


@pytest.mark.parametrize('query', CASES)
def test_cyclic_standard_order(query):
    from prolog.interpreter.continuation import Engine
    assert_true(query + '.', Engine(load_system=True))


def test_shared_graph_validation():
    # Validation must not expand all paths through this finite shared graph.
    goals = ['X0=f(A)']
    goals += ['X%d=f(X%d,X%d)' % (i, i-1, i-1) for i in range(1, 25)]
    goals += ['compare(>,X24,a)', 'var(A)']
    assert_true(', '.join(goals) + '.')


@pytest.mark.parametrize('query', [
    'compare(=, X, X), var(X)',
    'compare(_, X, Y), var(X), var(Y), X \\== Y',
    'X = a, Y = b, compare(<, X, Y)',
    'compare(<, 1, 2)',
    'compare(<, 1.5, 2.5)',
    'compare(<, 100000000000000000000, 100000000000000000001)',
    'X @< a, a @=< b, 2 @> 1, 2.0 @>= 1.0, var(X)',
    'put_attr(X, m, X), compare(=, X, X), var(X), get_attr(X, m, V), V == X',
])
def test_standard_order_leaf_operands_skip_cycle_traversal(monkeypatch, query):
    from prolog.builtin import type as prolog_type
    from prolog.interpreter.continuation import Engine
    engine = Engine(load_system=True)

    def unexpected_traversal(engine, heap, obj):
        pytest.fail('leaf operand entered the recursive cycle checker')

    monkeypatch.setattr(prolog_type, 'impl_acyclic_term', unexpected_traversal)
    assert_true(query + '.', engine)
