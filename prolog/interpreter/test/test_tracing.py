import py
from prolog.interpreter.test.tool import prolog_raises, \
assert_true, assert_false
from prolog.interpreter.parsing import get_engine
from prolog.interpreter.continuation import Engine

def test_simple_trace():
    e = Engine()
    assert_true("trace.", e)
    assert e.tracing == True
    assert_true("notrace.", e)
    assert e.tracing == False
    assert_true("trace, notrace.")
