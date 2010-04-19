import py
from prolog.interpreter.parsing import parse_file, TermBuilder
from prolog.interpreter.parsing import parse_query_term
from prolog.interpreter.error import UnificationFailed, CatchableError
from prolog.interpreter.continuation import Heap, Engine
from prolog.interpreter import error
from prolog.interpreter.test.tool import collect_all, assert_false, assert_true
from prolog.interpreter.test.tool import prolog_raises, get_engine

def test_assert_dynamic():
    e = get_engine("""
        :- dynamic f/1.
        f(a).
        f(b).
        g(a).
        g(b).
    """)
    heaps = collect_all(e, "f(X).")
    assert len(heaps) == 2
    assert_true("assert(f(c)).", e)

    heaps = collect_all(e, "f(X).")
    assert len(heaps) == 3

    prolog_raises("permission_error(modify, static_procedure, g/1)", "assert(g(c))", e)

def test_asserting_nonexisting_works():
    e = get_engine("""
        g(a).
        g(b).
    """)
    assert_true("assert(f(c)).", e)
    heaps = collect_all(e, "f(X).")
    assert len(heaps) == 1
    assert_true("assert(f(a)).", e)

    heaps = collect_all(e, "f(X).")
    assert len(heaps) == 2

def test_dynamic_after_rule():
    excinfo = py.test.raises(CatchableError, get_engine, """
        f(x).
        dynamic f/1.
        """)
    assert excinfo.value.term.name() == "error"
    eterm = excinfo.value.term.argument_at(0)
    assert eterm.name() == "permission_error"
