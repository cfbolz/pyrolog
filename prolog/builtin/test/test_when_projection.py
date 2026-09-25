import pytest

from prolog.interpreter.parsing import get_engine
from prolog.interpreter.test.tool import assert_true


SOURCE = '''
    restore([]).
    restore([Goal|Rest]) :- call(Goal), restore(Rest).
'''


@pytest.mark.parametrize('condition, copied', [
    ('nonvar(X)', 'nonvar(C)'),
    ('ground(f(X,Y))', 'ground(f(C,D))'),
    ('(nonvar(X),nonvar(Y))', '(nonvar(C),nonvar(D))'),
    ('(nonvar(X);nonvar(Y))', '(nonvar(C);nonvar(D))'),
    ('?=(X,Y)', '?=(C,D)'),
])
def test_when_projection_preserves_condition_and_sharing(condition, copied):
    engine = get_engine(SOURCE, load_system=True)
    assert_true('when(%s,Flag=ran), copy_term(t(X,Y,Flag),t(C,D,F),Goals), '
                'Goals == [coroutines:when(%s,user:(F=ran))], '
                'term_attvars(t(C,D,F,Goals),[]), '
                'C \\== X, D \\== Y, F \\== Flag.' % (condition, copied), engine)


CASES = [
    'when(nonvar(X),Flag=ran), copy_term(X-Flag,C-F,Goals), '
    'restore(Goals), var(F), C=a, F==ran, var(X), var(Flag)',
    'when(ground(f(X,Y)),Flag=ran), copy_term(t(X,Y,Flag),t(C,D,F),Goals), '
    'restore(Goals), C=a, var(F), D=b, F==ran, var(Flag)',
    'when((nonvar(X),nonvar(Y)),Flag=ran), '
    'copy_term(t(X,Y,Flag),t(C,D,F),Goals), '
    'restore(Goals), C=a, var(F), D=b, F==ran',
    'when((nonvar(X);nonvar(Y)),(var(Flag),Flag=ran)), '
    'copy_term(t(X,Y,Flag),t(C,D,F),Goals), '
    'restore(Goals), D=b, F==ran, C=a, var(Flag)',
    'when(?=(X,Y),Flag=ran), copy_term(t(X,Y,Flag),t(C,D,F),Goals), '
    'restore(Goals), var(F), C=D, F==ran, var(Flag)',
    'when((nonvar(X);nonvar(Y)),Flag=ran), X=a, '
    'copy_term(Y,C,Goals), Goals==[], var(C), Flag==ran',
    'when(nonvar(X),Flag=ran), copy_term(X,_,G1), copy_term(X,_,G2), '
    'G1=[_], G2=[_], X=a, Flag==ran',
    'when(nonvar(X),A=one), when(nonvar(X),B=two), '
    'copy_term(t(X,A,B),t(C,D,E),Goals), Goals=[_,_], '
    'restore(Goals), C=a, D==one, E==two',
    'when(nonvar(X),Flag=ran), dif(X,a), copy_term(X-Flag,C-F,Goals), '
    'restore(Goals), \\+ (C=a), C=b, F==ran, var(Flag)',
    'when((nonvar(X),ground(Y)),Flag=ran), X=a, '
    'copy_term(Y-Flag,C-F,Goals), restore(Goals), var(F), C=b, F==ran',
    'when(?=(f(X,Y),f(a,b)),Flag=ran), X=a, '
    'copy_term(Y-Flag,C-F,Goals), Goals=[_], restore(Goals), '
    'var(F), C=b, F==ran, var(Flag)',
    'when(nonvar(X),Flag=ran), \\+ copy_term(X,_,[]), '
    'copy_term(X,_,Goals), Goals=[_], X=a, Flag==ran',
    'when(nonvar(X),(Flag=one;Flag=two)), '
    'findall(Flag,X=a,Answers), Answers==[one,two], '
    'copy_term(X-Flag,C-F,Goals), restore(Goals), '
    'findall(F,C=a,Copied), Copied==[one,two]',
]


@pytest.mark.parametrize('query', CASES)
def test_when_projection_replay(query):
    assert_true(query + '.', get_engine(SOURCE, load_system=True))


def test_when_projection_preserves_goal_module():
    engine = get_engine(SOURCE + '''
        :- module(client, [delay/2]).
        delay(X, Y) :- when(nonvar(X), local_goal(Y)).
        local_goal(from_client).
        :- module(user).
    ''', load_system=True)
    assert_true('client:delay(X,Y), copy_term(X-Y,C-D,Goals), '
                'Goals == [coroutines:when(nonvar(C),client:local_goal(D))], '
                'restore(Goals), C=a, D==from_client.', engine)
