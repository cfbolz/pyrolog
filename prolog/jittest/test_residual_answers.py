import pytest
from prolog.jittest.support import run_log


@pytest.mark.parametrize('jit_options', ['off', 'threshold=40'])
def test_residual_answers(tmpdir, jit_options):
    log = run_log(tmpdir, '',
        'when(nonvar(X),Y=done), (true;X=a).\np\n;\n'
        'put_attr(X,missing,pair(Y,Y)), Z=f(X,Y).\n'
        'X=f(X), put_attr(Y,missing,X).\n', jit_options)
    assert log.result.count('coroutines:when(nonvar(X), user:(Y=done))') == 2
    assert 'X = a\nY = done' in log.result
    assert 'Z = f(X, Y)\nput_attr(X, missing, pair(Y, Y))' in log.result
    assert 'X = f(X)\nput_attr(Y, missing, X)' in log.result


@pytest.mark.parametrize('jit_options', ['off', 'threshold=40'])
def test_deep_answer(tmpdir, jit_options):
    source = '''
        deep(0, X, X) :- !.
        deep(N, Acc, X) :- M is N-1, deep(M, f(Acc), X).
    '''
    log = run_log(tmpdir, source, 'deep(3000,a,X).\n', jit_options)
    assert 'X = ' + 'f(' * 20 + '...' + ')' * 20 + '\n' in log.result
