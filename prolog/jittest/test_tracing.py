"""Run against a translated binary (set PYROLOG_EXECUTABLE to select it)."""
from rpython.tool.jitlogparser.parser import SimpleParser
from prolog.jittest.support import run_binary
import pytest


def test_compiled_loop_can_enable_tracing_and_run_again(tmpdir):
    source = """
    count(0) :- trace, leaf, notrace.
    count(N) :- N > 0, N1 is N - 1, count(N1).
    leaf.
    """
    queries = 'leash([-all]), once(count(3000)).\nonce(count(3000)).'
    output, loops = run_binary(tmpdir, source, queries)
    assert loops, 'the untraced recursion must compile'
    assert output.count('Call: (1) leaf') == 2
    assert output.count('Exit: (1) leaf') == 2
    assert 'Call: (1) count' not in output
    interpreted, unused = run_binary(tmpdir, source, queries, 'off')
    assert output == interpreted


def test_traced_recursion_stays_outside_jit(tmpdir):
    source = """
    count(0).
    count(N) :- N > 0, N1 is N - 1, count(N1).
    """
    queries = 'leash([-all]), trace, once(count(100)), notrace.'
    output, loops = run_binary(tmpdir, source, queries)
    assert not loops
    assert 'Call: (2) count(100)' in output
    assert 'Exit: (2) count(100)' in output
    interpreted, unused = run_binary(tmpdir, source, queries, 'off')
    assert output == interpreted


def test_compiled_console_stepping_and_redo(tmpdir):
    queries = 'trace.\np(X).\n\n\n;\n\n\nnotrace.'
    output, loops = run_binary(tmpdir, 'p(a). p(b).', queries)
    assert 'X = a' in output and 'X = b' in output
    assert 'Redo: (1) p(_G0)' in output
    assert output.count('Call: (1) p') == 1


def test_untraced_loop_still_eliminates_interpreter_allocations(tmpdir):
    source = """
    count(0).
    count(N) :- N1 is N - 1, count(N1).
    """
    output, loops = run_binary(tmpdir, source, 'once(count(3000)).')
    assert loops
    assert 'Call:' not in output
    for loop in loops:
        assert 'new_with_vtable' not in loop
        assert 'new_array' not in loop
    assert any('int_sub_ovf' in loop for loop in loops)


def test_compiled_tracing_keeps_attributed_catcher_hooks(tmpdir):
    query = ('once((leash([-all]), trace, freeze(X, Y = a), '
             'catch(throw(ball), X, true), Y == a, notrace)).')
    output, loops = run_binary(tmpdir, '', query)
    assert 'Y = a' in output
    assert 'Nein' not in output


def test_meta_call_hot_loop_keeps_only_arithmetic_and_guards(tmpdir):
    # The historical test_iterate.test_call workload, parsed without that
    # harness's assumptions about the old JIT log chunk layout.
    source = """
    iterate_call(X) :- c(X, c).
    c(0, _).
    c(X, Pred) :- Y is X - 1, C =.. [Pred, Y, Pred], call(C).
    """
    output, loops = run_binary(tmpdir, source, 'once(iterate_call(3000)).')
    assert loops
    for loop in loops:
        operations = SimpleParser.parse_from_input(loop).operations
        labels = [i for i, op in enumerate(operations) if op.name == 'label']
        # The last label begins the hot loop after its entry preamble.
        names = [op.name for op in operations[labels[-1] + 1:]
                 if op.name != 'debug_merge_point']
        assert 'int_sub_ovf' in names
        assert set(names) <= set(['guard_not_invalidated', 'int_sub_ovf',
                                 'guard_no_overflow', 'int_is_zero', 'int_eq',
                                 'guard_false', 'jump'])


@pytest.mark.parametrize('queries, expected', [
    ('', 'welcome!'),
    ('true.', 'yes'),
    ('halt.', 'welcome!'),
    ('(X = a; X = b).\n', 'X = a'),
    ('trace.\ntrue.\n', 'Call: (1) true'),
    ('trace.\ntrue.\n\n', 'Exit: (1) true'),
])
def test_compiled_console_eof(tmpdir, queries, expected):
    output, loops = run_binary(tmpdir, '', queries, send_halt=False)
    assert expected in output
    if queries != 'halt.':
        assert output.endswith('\n')


def test_compiled_eof_during_startup_directive(tmpdir):
    output, loops = run_binary(tmpdir, ':- trace, true.', '', send_halt=False)
    assert 'Call: (1) true' in output
    assert 'welcome!' not in output
