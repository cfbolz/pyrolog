import pytest

from prolog.jittest.support import run_log


@pytest.mark.parametrize('query', [
    'findall(X, reverse(X, [a,b,c]), L), L == [[c,b,a]]',
    'X = f(X), reverse([X,a], R), R == [a,X]',
])
def test_compiled_reverse(tmpdir, query):
    log = run_log(tmpdir, '', 'once((%s, write(check_passed), nl)).' % query)
    assert 'check_passed\n' in log.result
    assert 'Nein' not in log.result
