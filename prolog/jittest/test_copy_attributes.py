import pytest
from prolog.builtin.test.test_copy_attributes import CASES, SOURCE, PROJECTION_SOURCE
from prolog.jittest.support import run_log


@pytest.mark.parametrize('query', CASES)
def test_compiled_copy_attributes(tmpdir, query):
    log = run_log(tmpdir, SOURCE, 'once((%s, write(check_passed), nl)).' % query)
    assert 'check_passed\n' in log.result
    assert 'Nein' not in log.result


@pytest.mark.parametrize('jit_options', ['off', 'threshold=40'])
def test_compiled_attribute_goals(tmpdir, jit_options):
    source = PROJECTION_SOURCE + '\n:- module(user).\n' + SOURCE + '''
        loop(0) :- !.
        loop(N) :-
            put_attr(X,projected,pair(Y,Y)),
            copy_term(pair(X,Y),pair(C,D),G),
            G == [projected:restore(C,pair(D,D))],
            term_attvars(C-D-G,[]),
            restore_attributes(G), get_attr(C,projected,pair(D,D)),
            get_attr(X,projected,pair(Y,Y)),
            N1 is N-1, loop(N1).
    '''
    log = run_log(tmpdir, source, 'loop(100), write(projection_passed), nl.\n',
                  jit_options)
    assert 'projection_passed\n' in log.result
