import pytest

from prolog.jittest.support import run_log


@pytest.mark.parametrize('setup, comparison, comparator_calls', [
    ('true', 'X == X', 0),
    ('X = f(X)', 'X == X', 0),
    ('put_attr(X, missing_hook, X)', 'X == X', 0),
    ('X = a, Y = a', 'X == Y', 0),
    ('X = a, Y = b', 'X \\== Y', 1),
    ('X = a, Y = b', '(X == Y -> fail; true)', 1),
    ('X is 1 + 0, Y is 2 - 1', 'X == Y', 0),
    ('X = 1, Y = 2', 'X \\== Y', 0),
    ('X is 1.5 + 0.0, Y is 3.0 / 2.0', 'X == Y', 0),
    ('X = 1.5, Y = 2.5', 'X \\== Y', 0),
])
def test_identity_fast_path_loop(tmpdir, setup, comparison, comparator_calls):
    source = """
    identity_loop(0, _, _) :- !.
    identity_loop(N, X, Y) :-
        %s,
        N1 is N - 1,
        identity_loop(N1, X, Y).
    """ % comparison
    query = 'once((%s, identity_loop(3000, X, Y), write(check_passed), nl)).' % setup
    log = run_log(tmpdir, source, query)
    assert 'check_passed\n' in log.result
    loops = log.filter_loops('identity_loop/3')
    assert loops, 'identity loop must compile'
    operations = [op for loop in log.loops for op in loop.allops()]
    assert not any('identity_visit' in str(op) for op in operations)
    if comparator_calls:
        # Atom ordering currently remains out of line. Require exactly one
        # comparator call in the hot loop, with no heap argument materialized.
        operations = [op for loop in loops for op in loop.allops()]
    calls = [op for op in operations if op.name.startswith('call')]
    assert len(calls) == comparator_calls, '\n'.join(map(str, calls))
    for call in calls:
        assert call.name == 'call_i'
        assert call.args[-1] == 'ConstPtr(null)'
