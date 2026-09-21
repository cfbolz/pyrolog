"""Run against a translated binary (set PYROLOG_EXECUTABLE to select it)."""
import pytest
from prolog.jittest.support import run_log


def test_compiled_loop_can_enable_tracing_and_run_again(tmpdir):
    source = """
    count(0) :- trace, leaf, notrace.
    count(N) :- N > 0, N1 is N - 1, count(N1).
    leaf.
    """
    queries = 'leash([-all]), once(count(3000)).\nonce(count(3000)).'
    log = run_log(tmpdir, source, queries)
    assert log.loops, 'the untraced recursion must compile'
    assert log.result.count('Call: (1) leaf') == 2
    assert log.result.count('Exit: (1) leaf') == 2
    assert 'Call: (1) count' not in log.result
    interpreted = run_log(tmpdir, source, queries, 'off')
    assert log.result == interpreted.result


def test_traced_recursion_stays_outside_jit(tmpdir):
    source = """
    count(0).
    count(N) :- N > 0, N1 is N - 1, count(N1).
    """
    queries = 'leash([-all]), trace, once(count(100)), notrace.'
    log = run_log(tmpdir, source, queries)
    assert not log.loops
    assert 'Call: (2) count(100)' in log.result
    assert 'Exit: (2) count(100)' in log.result
    interpreted = run_log(tmpdir, source, queries, 'off')
    assert log.result == interpreted.result


def test_compiled_console_stepping_and_redo(tmpdir):
    queries = 'trace.\np(X).\n\n\n;\n\n\nnotrace.'
    log = run_log(tmpdir, 'p(a). p(b).', queries)
    assert 'X = a' in log.result and 'X = b' in log.result
    assert 'Redo: (1) p(_G0)' in log.result
    assert log.result.count('Call: (1) p') == 1


def test_untraced_loop_still_eliminates_interpreter_allocations(tmpdir):
    source = """
    count(0).
    count(N) :- N1 is N - 1, count(N1).
    """
    log = run_log(tmpdir, source, 'once(count(3000)).')
    assert log.loops
    assert 'Call:' not in log.result
    # Inspect full traces, including entry preambles, not just hot loops.
    names = [op.name for loop in log.loops for op in loop.allops()]
    assert not any(name.startswith('new') for name in names)
    assert 'int_sub_ovf' in names


def test_compiled_tracing_keeps_attributed_catcher_hooks(tmpdir):
    query = ('once((leash([-all]), trace, freeze(X, Y = a), '
             'catch(throw(ball), X, true), Y == a, notrace)).')
    log = run_log(tmpdir, '', query)
    assert 'Y = a' in log.result
    assert 'Nein' not in log.result


@pytest.mark.parametrize('queries, expected', [
    ('', 'welcome!'),
    ('true.', 'yes'),
    ('halt.', 'welcome!'),
    ('(X = a; X = b).\n', 'X = a'),
    ('trace.\ntrue.\n', 'Call: (1) true'),
    ('trace.\ntrue.\n\n', 'Exit: (1) true'),
])
def test_compiled_console_eof(tmpdir, queries, expected):
    log = run_log(tmpdir, '', queries, send_halt=False)
    assert expected in log.result
    if queries != 'halt.':
        assert log.result.endswith('\n')


def test_compiled_eof_during_startup_directive(tmpdir):
    log = run_log(tmpdir, ':- trace, true.', '', send_halt=False)
    assert 'Call: (1) true' in log.result
    assert 'welcome!' not in log.result
