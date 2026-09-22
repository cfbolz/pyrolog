import pytest

from prolog.interpreter.test.test_rational_tree_collectors import (
    FINDALL_CASES, NUMBERVARS_CASES, VARIANT_CASES)
from prolog.jittest.support import run_log


@pytest.mark.parametrize('query', FINDALL_CASES + NUMBERVARS_CASES + VARIANT_CASES)
def test_compiled_rational_tree_collectors(tmpdir, query):
    log = run_log(tmpdir, '', 'once((%s, write(check_passed), nl)).' % query)
    assert 'check_passed\n' in log.result
    assert 'Nein' not in log.result
