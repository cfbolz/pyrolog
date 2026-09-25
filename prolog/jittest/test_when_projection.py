import pytest

from prolog.jittest.support import run_log
from prolog.builtin.test.test_when_projection import CASES, SOURCE


@pytest.mark.parametrize('jit_options', ['off', 'threshold=40'])
def test_compiled_when_projection(tmpdir, jit_options):
    source = SOURCE
    for index, query in enumerate(CASES):
        source += '\ncheck_%s :- %s.\n' % (index, query)
    checks = ', '.join('check_%s' % index for index in range(len(CASES)))
    source += '''
        loop(0) :- !.
        loop(N) :- %s, N1 is N-1, loop(N1).
    ''' % checks
    log = run_log(tmpdir, source, 'loop(100), write(when_passed), nl.\n',
                  jit_options)
    assert 'when_passed\n' in log.result
