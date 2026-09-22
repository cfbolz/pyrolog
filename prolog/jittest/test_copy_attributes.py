import pytest
from prolog.builtin.test.test_copy_attributes import CASES, SOURCE
from prolog.jittest.support import run_log


@pytest.mark.parametrize('query', CASES)
def test_compiled_copy_attributes(tmpdir, query):
    log = run_log(tmpdir, SOURCE, 'once((%s, write(check_passed), nl)).' % query)
    assert 'check_passed\n' in log.result
    assert 'Nein' not in log.result
