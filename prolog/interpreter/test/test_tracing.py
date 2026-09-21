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


class ScriptedIO(object):
    def __init__(self, commands):
        self.commands = list(commands)
        self.output = []

    def read_command(self):
        assert self.commands, 'unexpected debugger prompt'
        return self.commands.pop(0)

    def write(self, text):
        self.output.append(text)


def console_engine(source, commands):
    e = get_engine(source)
    io = ScriptedIO(commands)
    e.debugger.observer.io = io
    e.debugger.enable()
    return e, io


def test_console_skip_and_goal_display():
    e, io = console_engine("p :- q. q.", ['g', 'p', 'w', 'h', 'r', 'f', 's', '\n'])
    assert_true("p.", e)
    output = ''.join(io.output)
    assert 'Call: (1) p' in output
    assert 'Exit: (1) p' in output
    assert 'Call: (2)' not in output
    assert '[1] p' in output
    assert 'not implemented yet' in output
    assert not io.commands
    assert e.debugger.skip_frame is None


@py.test.mark.parametrize('source, query, port', [
    ('p :- fail.', 'p.', 'Fail'),
    ('p :- missing.', 'p.', 'Exception'),
])
def test_skip_stops_at_failure_or_exception(source, query, port):
    e, io = console_engine(source, ['s', '\n'])
    py.test.raises((error.UnificationFailed, error.UncaughtError), assert_true, query, e)
    assert port + ': (1) p' in ''.join(io.output)
    assert not io.commands
    assert e.debugger.skip_frame is None


def test_leashing_and_tracing_predicate():
    e, io = console_engine('p.', [])
    assert_true('leash([-all]), tracing, p.', e)
    assert ''.join(io.output) == 'Call: (1) p\nExit: (1) p\n'
    assert_true('leash([+call,+fail]).', e)
    assert sorted(e.debugger.leashed) == ['Call', 'Fail']
    assert_true('leash([+all,-exception]).', e)
    assert sorted(e.debugger.leashed) == ['Call', 'Exit', 'Fail', 'Redo']
    assert_true('notrace.', e)
    assert_false('tracing.', e)


@py.test.mark.parametrize('query', [
    'leash(X).', 'leash([X]).', 'leash([+X]).',
    'leash([+]).', 'leash([+missing]).', 'leash([+1]).',
    'leash([-all,+missing]).',
])
def test_invalid_leash_is_atomic(query):
    e = Engine()
    before = e.debugger.leashed.copy()
    py.test.raises(error.UncaughtError, assert_true, query, e)
    assert e.debugger.leashed == before


def test_leap_disables_output_but_preserves_backtracking():
    e, io = console_engine('p(a). p(b).', ['l'])
    answers = collect_all(e, 'p(X).')
    assert [answer['X'].name() for answer in answers] == ['a', 'b']
    assert ''.join(io.output) == 'Call: (1) p(_G0) ? Tracing disabled.\n'
    assert not e.debugger.enabled


def test_abort_is_not_caught_by_prolog_and_clears_debug_state():
    from prolog.interpreter.traceconsole import DebugAbort
    e, io = console_engine('p.', ['a'])
    py.test.raises(DebugAbort, assert_true, 'catch(p, X, true).', e)
    assert e.debugger.query_depth == 0
    assert e.debugger.skip_frame is None
    io.commands = ['\n', '\n']
    assert_true('p.', e)
    assert not io.commands


def test_console_queries_and_answer_redo(monkeypatch):
    from prolog.interpreter import translatedmain
    e = get_engine('p(a). p(b).')
    lines = iter(['trace.\n', 'p(X).\n', '\n', '\n', ';\n',
                  '\n', '\n', 'notrace.\n', 'halt.\n'])
    output = []
    monkeypatch.setattr(translatedmain, 'readline', lambda: next(lines))
    monkeypatch.setattr(translatedmain, 'printmessage', output.append)
    translatedmain.repl(e)
    output = ''.join(output)
    assert '[trace] >?- ' in output
    assert 'X = a' in output and 'X = b' in output
    assert 'Redo: (1) p(_G0)' in output
    assert output.count('Call: (1) p') == 1
    assert not e.debugger.enabled


def test_console_abort_returns_to_prompt(monkeypatch):
    from prolog.interpreter import translatedmain
    e = get_engine('p.')
    lines = iter(['trace.\n', 'p.\n', 'a\n', 'notrace.\n', 'p.\n', 'halt.\n'])
    output = []
    monkeypatch.setattr(translatedmain, 'readline', lambda: next(lines))
    monkeypatch.setattr(translatedmain, 'printmessage', output.append)
    translatedmain.repl(e)
    assert 'Execution aborted\n' in output
    assert output.count('yes\n') == 3
