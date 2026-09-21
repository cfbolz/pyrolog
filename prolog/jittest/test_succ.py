import pytest

from prolog.jittest.support import run_log


@pytest.mark.parametrize('query', [
    # Crossing the machine-integer boundary in each direction.
    'succ(9223372036854775807, X), X == 9223372036854775808, '
    'succ(Y, X), Y == 9223372036854775807',
    'succ(1000000000000000000000000000000, X), '
    'X == 1000000000000000000000000000001',
    'not(succ(_, 0)), '
    'catch((succ(_, _), fail), error(instantiation_error), true), '
    'catch((succ(0, -1), fail), '
    'error(domain_error(not_less_than_zero, -1)), true)',
])
def test_compiled_succ(tmpdir, query):
    log = run_log(tmpdir, '', 'once((%s, write(check_passed), nl)).' % query)
    assert 'check_passed\n' in log.result
    assert 'Nein' not in log.result
