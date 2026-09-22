import pytest
from prolog.builtin.test.test_variant import CASES
from prolog.jittest.support import run_log


@pytest.mark.parametrize('query', CASES)
def test_compiled_variant(tmpdir, query):
    log = run_log(tmpdir, '', 'once((%s, write(check_passed), nl)).' % query)
    assert 'check_passed\n' in log.result
    assert 'Nein' not in log.result
