import pytest
from prolog.jittest.support import run_log


@pytest.mark.parametrize('query, expected', [
    ('_X=f(_X), write(_X)', '@(_G0, [_G0=f(_G0)])'),
    ('_X=[a|_X], write(_X)', '@(_G0, [_G0=[a|_G0]])'),
    ('_X=[a|_X], write_term(_X,[max_depth(3)])', '[a, a|...]'),
    ('_X=f(_X), catch((write_term(_X,[cycles(false)]),fail), '
     'error(domain_error(cyclic_term,_)),write(rejected))', 'rejected'),
])
def test_compiled_cyclic_output(tmpdir, query, expected):
    log = run_log(tmpdir, '', 'once((%s)).' % query)
    assert expected in log.result
    assert 'yes' in log.result
    assert 'Nein' not in log.result
