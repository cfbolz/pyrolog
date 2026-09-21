"""Tests for the Prolog adapter; matcher tests live upstream in PyPy."""
import pytest
from pypy.module.pypyjit.test_pypy_c.model import InvalidMatch
from prolog.jittest.model import Log


def test_predicate_selection_and_loop_sections():
    rawtrace = """
    # Loop 0 (c/2 RuleContinuationSize4) : loop with 7 ops
    [i0]
    label(i0, descr=TargetToken(1))
    debug_merge_point(0, 0, 'c/2 RuleContinuationSize4')
    i1 = int_add(i0, 1)
    label(i1, descr=TargetToken(2))
    debug_merge_point(0, 0, 'c/2 BuiltinContinuation')
    i2 = int_sub(i1, 1)
    jump(i2, descr=TargetToken(2))
    """
    log = Log([rawtrace])
    # Bookkeeping precedes the first location; no Python bytecode is involved.
    assert log.loops[0].chunks[0].bytecode_name is None
    loop, = log.filter_loops('c/2')
    assert loop.match("""
        i_next = int_sub(i_current, 1)
        jump(i_next, descr=...)
    """)
    assert not log.filter_loops('c')
    assert not log.filter_loops('c/1')
    assert not log.filter_loops('Continuation')
    preamble, = log.filter_loops('c/2', is_entry_bridge=True)
    assert preamble.match("i_next = int_add(i_current, 1)")
    assert log.filter_loops('c/2', is_entry_bridge='*') == log.loops
    # Exercise the inherited matcher API: mismatches raise, not return False.
    with pytest.raises(InvalidMatch):
        loop.match("i_next = int_sub(i_current, 2)\njump(i_next, descr=...)")
