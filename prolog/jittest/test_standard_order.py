import pytest
from prolog.interpreter.test.test_cyclic_standard_order import CASES
from prolog.jittest.support import run_log


@pytest.mark.parametrize('query', CASES)
def test_compiled_standard_order(tmpdir, query):
    log = run_log(tmpdir, '', 'once((%s, write(check_passed), nl)).' % query)
    assert 'check_passed\n' in log.result
    assert 'Nein' not in log.result
