import py
from prolog.interpreter.test.tool import prolog_raises, \
assert_true, assert_false
from prolog.interpreter.parsing import get_engine
from prolog.interpreter.continuation import Engine
from prolog.interpreter import error
from prolog.interpreter.trace import TraceObserver, format_goal
from prolog.interpreter.test.tool import collect_all


class RecordingObserver(TraceObserver):
    def __init__(self):
        self.events = []

    def event(self, engine, port, frame):
        self.events.append((port, frame.depth, format_goal(engine, frame, port)))


def traced_engine(source="", load_system=False):
    engine = get_engine(source, load_system=load_system)
    observer = RecordingObserver()
    engine.debugger.observer = observer
    engine.debugger.enable()
    return engine, observer.events

def test_simple_trace():
    assert_true("trace.")
    assert_true("notrace.")


def test_ports_and_call_before_head_matching():
    e, events = traced_engine("p(a). p(b).")
    answers = collect_all(e, "p(X).")
    assert [answer['X'].name() for answer in answers] == ['a', 'b']
    assert events == [('Call', 1, 'p(_G0)'), ('Exit', 1, 'p(a)'),
                      ('Redo', 1, 'p(_G0)'), ('Exit', 1, 'p(b)'),
                      ('Fail', 1, 'p(_G0)')]
    del events[:]
    assert_false("p(c).", e)
    assert events == [('Call', 1, 'p(c)'), ('Fail', 1, 'p(c)')]


def test_nested_calls_and_sibling_depth():
    e, events = traced_engine("p(X) :- q(X), r(X). q(a). r(a).")
    assert_true("p(X).", e)
    assert events == [('Call', 1, 'p(_G0)'), ('Call', 2, 'q(_G0)'),
                      ('Exit', 2, 'q(a)'), ('Call', 2, 'r(a)'),
                      ('Exit', 2, 'r(a)'), ('Exit', 1, 'p(a)')]


def test_fail_restores_call_bindings():
    e, events = traced_engine("p(X) :- X = a, fail.")
    assert_false("p(X).", e)
    assert events[-1] == ('Fail', 1, 'p(_G0)')


def test_undefined_predicate_and_exception_unwinding():
    e, events = traced_engine("p :- missing.")
    py.test.raises(error.UncaughtError, assert_true, "p.", e)
    assert events == [('Call', 1, 'p'), ('Call', 2, 'missing'),
                      ('Exception', 2, 'missing'), ('Exception', 1, 'p')]


def test_caught_exception_keeps_outer_frame():
    e, events = traced_engine("p :- catch(throw(ball), ball, true).")
    assert_true("p.", e)
    assert [(port, depth) for port, depth, goal in events] == [
        ('Call', 1), ('Call', 2), ('Call', 3), ('Exception', 3),
        ('Call', 3), ('Exit', 3), ('Exit', 2), ('Exit', 1)]


@py.test.mark.parametrize('body, expected', [
    ('(X = a; X = b)', ['a', 'b']),
    ('(X = a; X = b), !', ['a']),
    ('once((X = a; X = b))', ['a']),
    ('((X = a; X = b) -> true; X = c)', ['a']),
    ('\\+ fail, X = a', ['a']),
    ('call((X = a; X = b))', ['a', 'b']),
    ('repeat, X = a, !', ['a']),
    ('catch((X = b, throw(ball)), ball, X = a)', ['a']),
])
def test_tracing_preserves_search(body, expected):
    e, events = traced_engine("p(X) :- %s." % body)
    answers = collect_all(e, "p(X).")
    assert [answer['X'].name() for answer in answers] == expected


def test_enable_disable_and_enable_again():
    e, events = traced_engine("p :- notrace, true, trace, q. q.")
    assert_true("p.", e)
    assert events == [('Call', 1, 'p'), ('Call', 1, 'q'), ('Exit', 1, 'q')]
    del events[:]
    assert_true("q.", e)
    assert events == [('Call', 1, 'q'), ('Exit', 1, 'q')]


def test_disabled_tracing_allocates_no_frames(monkeypatch):
    from prolog.interpreter import trace
    def unexpected(*args):
        raise AssertionError('allocated a debug frame with tracing disabled')
    monkeypatch.setattr(trace.DebugFrame, '__init__', unexpected)
    e = get_engine("p(a).")
    assert_true("p(X).", e)


def test_findall_and_attribute_hooks():
    e, events = traced_engine(load_system=True)
    assert_true("findall(X, (X = a; X = b), [a,b]).", e)
    assert_true("freeze(X, Y = a), X = b, Y == a.", e)
