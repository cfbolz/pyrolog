import pytest

from prolog.jittest.support import run_log


@pytest.mark.parametrize('setup, goal', [
    ('L = [f|L]', 'T =.. L'),
    ('Tail = [b,c|Tail], L = [a|Tail]', 'atom_chars(A, L)'),
    ('L = [49|L]', 'number_codes(1, L)'),
    ('L = [quoted(true)|L]', 'write_term(a, L)'),
])
def test_compiled_cyclic_list_error(tmpdir, setup, goal):
    query = ('once((%s, catch((%s, fail), error(type_error(list, C)), '
             'C == L), write(cycle_rejected), nl)).' % (setup, goal))
    log = run_log(tmpdir, '', query)
    assert 'cycle_rejected\n' in log.result
    assert 'Nein' not in log.result
