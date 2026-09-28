import pytest
from prolog.interpreter.test.test_cyclic_standard_order import CASES
from prolog.jittest.support import run_log


@pytest.mark.parametrize('query', CASES)
def test_compiled_standard_order(tmpdir, query):
    log = run_log(tmpdir, '', 'once((%s, write(check_passed), nl)).' % query)
    assert 'check_passed\n' in log.result
    assert 'Nein' not in log.result


@pytest.mark.parametrize('arguments', [
    # Different-type comparisons avoid the separate out-of-line helpers for
    # variable IDs, atom ordering and bigint arithmetic.
    'X, a',
    'a, 1',
    '1, 2',
    '1.5, 2.5',
    '100000000000000000000, a',
])
def test_leaf_order_loop_has_no_calls(tmpdir, arguments):
    source = """
    leaf_order_loop(0, _, _) :- !.
    leaf_order_loop(N, X, Y) :-
        compare(_, X, Y),
        N1 is N - 1,
        leaf_order_loop(N1, X, Y).
    """
    query = 'once((leaf_order_loop(3000, %s), write(check_passed), nl)).' % arguments
    log = run_log(tmpdir, source, query)
    assert 'check_passed\n' in log.result
    assert log.filter_loops('leaf_order_loop/3'), 'comparison loop must compile'
    # Include entry preambles, not just the hot loop body.
    operations = [op for loop in log.loops for op in loop.allops()]
    calls = [op for op in operations if op.name.startswith('call')]
    assert not calls, '\n'.join(map(str, calls))
