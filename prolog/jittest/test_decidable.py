import pytest
from prolog.interpreter.test.test_strictly_identical_or_not_unifiable import CASES
from prolog.jittest.support import run_log


@pytest.mark.parametrize('query', CASES)
def test_compiled_decidable(tmpdir, query):
    log = run_log(tmpdir, '', 'once((%s, write(check_passed), nl)).' % query)
    assert 'check_passed\n' in log.result
    assert 'Nein' not in log.result
