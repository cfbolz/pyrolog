import pytest
from prolog.jittest.support import run_log


@pytest.mark.parametrize('query', [
    'L = [1|L], catch((length(L,N),fail), error(type_error(list,C)), C == L)',
    'catch((length(a,N),fail), error(type_error(list,a)), true)',
    'catch((length(L,-1),fail), error(domain_error(not_less_than_zero,-1)), true)',
    'not(length(L,L)), not(length([a|N],N))',
    'findall(L,length(L,3),Ls), Ls = [[_,_,_]]',
    'length([a|T],3), T = [_,_], X = f(X), length([X],1)',
    'not(is_list(L)), var(L), X = [a|X], not(is_list(X)), '
    'Y = f(Y), is_list([Y])',
    'not(length([a],1000000000000000000000000000000))',
])
def test_compiled_length_and_is_list(tmpdir, query):
    log = run_log(tmpdir, '', 'once((%s, write(check_passed), nl)).' % query)
    assert 'check_passed\n' in log.result
    assert 'Nein' not in log.result
