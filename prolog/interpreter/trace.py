"""Predicate-call tracing. Debug frames never serve as execution frames.

The extra continuations delimit calls and observe success/backtracking; clause
selection and the actual alternatives remain the engine's responsibility.
"""
from rpython.rlib import jit
from prolog.interpreter import error, term
from prolog.interpreter.continuation import (
    Continuation, ContinuationWithRule, FailureContinuation,
    DoneSuccessContinuation, _process_hooks)


class TraceObserver(object):
    def event(self, engine, port, frame):
        pass


class Debugger(object):
    # Switching tracing invalidates compiled assumptions about the normal path.
    _immutable_fields_ = ["enabled?"]

    def __init__(self):
        from prolog.interpreter.traceconsole import ConsoleTraceObserver
        self.enabled = False
        self.generation = 0
        self.observer = ConsoleTraceObserver()
        self.leashed = {"Call": True, "Exit": True, "Redo": True,
                        "Fail": True, "Exception": True}
        self.skip_frame = None
        self.query_depth = 0

    def enable(self):
        if not self.enabled:
            self.generation += 1
        self.enabled = True

    def disable(self):
        self.enabled = False
        self.skip_frame = None

    def enter_query(self):
        self.query_depth += 1

    def leave_query(self):
        self.query_depth -= 1
        if self.query_depth == 0:
            self.skip_frame = None

    def event(self, engine, port, frame):
        if self.enabled and frame.generation == self.generation:
            if self.skip_frame is not None:
                if self.skip_frame is frame and port in ("Exit", "Fail", "Exception"):
                    self.skip_frame = None
                else:
                    return
            self.observer.event(engine, port, frame)


class DebugFrame(object):
    def __init__(self, query, parent, generation):
        self.query = query
        self.parent = parent
        self.generation = generation
        self.depth = 1
        if parent is not None:
            self.depth = parent.depth + 1
        self.call_text = ""


def format_goal(engine, frame, port):
    from prolog.builtin.formatting import TermFormatter
    # At Redo, alternatives have not yet restored their bindings. Display the
    # call-time snapshot instead of a value left over from the last solution.
    if port == "Redo":
        return frame.call_text
    return TermFormatter(engine, quoted=True, max_depth=20).format(frame.query)


def should_trace(query):
    query = query.dereference(None)
    if isinstance(query, term.Callable):
        sig = query.signature()
        if sig.numargs == 2 and sig.name in (",", ";", "->", ":"):
            return False
        if sig.numargs == 0 and sig.name in ("!", "trace", "notrace", "tracing"):
            return False
        if sig.numargs == 1 and sig.name == "leash":
            return False
    return True


def trace_call(engine, query, rule, scont, fcont, heap):
    parent = None
    cont = scont
    while cont is not None and not cont.is_done():
        if (isinstance(cont, DebugExitContinuation) and
                cont.frame.generation == engine.debugger.generation):
            parent = cont.frame
            break
        cont = cont.nextcont
    frame = DebugFrame(query, parent, engine.debugger.generation)
    failure = DebugFailureContinuation(engine, scont, fcont, heap, frame)
    exitcont = DebugExitContinuation(engine, scont, frame, failure)
    return DebugCallContinuation(engine, rule, exitcont, frame), failure, heap.branch()


class DebugCallContinuation(ContinuationWithRule):
    def __init__(self, engine, rule, nextcont, frame):
        ContinuationWithRule.__init__(self, engine, nextcont, rule)
        self.frame = frame

    def activate(self, fcont, heap):
        self.frame.call_text = format_goal(self.engine, self.frame, "Call")
        self.engine.debugger.event(self.engine, "Call", self.frame)
        return self.engine._call(self.frame.query, self.rule,
                                 self.nextcont, fcont, heap)


class DebugExitContinuation(Continuation):
    def __init__(self, engine, nextcont, frame, failure):
        Continuation.__init__(self, engine, nextcont)
        self.frame = frame
        self.failure = failure

    def activate(self, fcont, heap):
        self.engine.debugger.event(self.engine, "Exit", self.frame)
        if has_alternatives(fcont, self.failure):
            fcont = DebugRedoContinuation(self.engine, fcont, self.frame)
        return self.nextcont, fcont, heap


class ResumeFailureContinuation(Continuation):
    def activate(self, fcont, heap):
        return fcont.fail(heap)


class DebugFailureContinuation(FailureContinuation):
    def __init__(self, engine, nextcont, fcont, heap, frame):
        FailureContinuation.__init__(self, engine, nextcont, fcont, heap)
        self.frame = frame

    def fail(self, heap):
        heap = heap.revert_upto(self.undoheap, discard_choicepoint=True)
        self.engine.debugger.event(self.engine, "Fail", self.frame)
        return (ResumeFailureContinuation(self.engine, self.nextcont),
                self.orig_fcont, heap)

    def has_choices(self):
        return has_alternatives(self, None)


class DebugRedoContinuation(FailureContinuation):
    def __init__(self, engine, inner, frame):
        FailureContinuation.__init__(self, engine, inner.nextcont, inner, None)
        self.frame = frame

    def fail(self, heap):
        self.engine.debugger.event(self.engine, "Redo", self.frame)
        return (ResumeFailureContinuation(self.engine, self.nextcont),
                self.orig_fcont, heap)

    def cut(self, upto, heap):
        # This observer owns no heap checkpoint.
        if self is not upto:
            self.orig_fcont.cut(upto, heap)

    def has_choices(self):
        return has_alternatives(self, None)


def has_alternatives(fcont, stop):
    while fcont is not stop:
        if fcont.is_done():
            return False
        if not isinstance(fcont, (DebugFailureContinuation, DebugRedoContinuation)):
            return True
        fcont = fcont.orig_fcont
    return False


@jit.dont_look_inside
def debug_driver(scont, fcont, heap):
    """Stay outside the JIT for the rest of this query, even after notrace.

Outstanding debug delimiters must still unwind when tracing is switched off.
    """
    rule = None
    while not scont.is_done():
        if isinstance(scont, ContinuationWithRule):
            rule = scont.rule
        try:
            scont, fcont, heap = scont.activate(fcont, heap)
        except error.UnificationFailed:
            scont, fcont, heap = fcont.fail(heap)
        except error.CatchableError, exc:
            scont, fcont, heap = scont.engine.throw(exc, scont, fcont, heap, rule)
        else:
            scont, fcont, heap = _process_hooks(scont, fcont, heap)
    assert isinstance(scont, DoneSuccessContinuation)
    if scont.failed:
        raise error.UnificationFailed
