import os, sys
from pypy.rlib import jit
from pypy.rlib.objectmodel import we_are_translated, specialize
import prolog.interpreter.continuation
from prolog.interpreter import error, term
import prolog.interpreter.term
prolog.interpreter.term.DEBUG = False

class StopItNow(Exception):
    pass

def getch():
    line = readline()
    return line[0]

def debug(msg):
    os.write(2, "debug: " + msg + '\n')

def printmessage(msg):
    os.write(1, msg)

def readline():
    result = []
    while 1:
        s = os.read(0, 1)
        result.append(s)
        if s == "\n":
            break
        if s == '':
            if len(result) > 1:
                break
            raise SystemExit
    return "".join(result)

tracehelptext = """
key    action
-------------
enter  creep
a      abort
"""

# ___________________________________________________________________
# TraceContinuation classes

class TraceContinuation(object):
    """ Represents a continuation of the Prolog computation. This can be seen
    as an RPython-compatible way to express closures. This class and its sub-
    classes are used for tracing only. """

    def __init__(self, engine, nextcont):
        self.engine = engine
        self.nextcont = nextcont
        if nextcont is not None:
            self._candiscard = nextcont.candiscard()
        else:
            self._candiscard = False

    def candiscard(self):
        return self._candiscard

    def activate(self, fcont, heap):
        """ Follow the continuation. heap is the heap that should be used while
        doing so, fcont the failure continuation that should be activated in
        case this continuation fails. This method can only be called once, i.e.
        it can destruct this object. 
        
        The method should return a triple (next cont, failure cont, heap)"""
        raise NotImplementedError("abstract base class")

    def is_done(self):
        return False

    def discard(self):
        """ Discard the information stored in a Continuation. This will be used
        if a SuccessContinuation will no longer be activatable, since
        backtracking occurred. """
        if self.nextcont is not None:
            self.nextcont.discard()
    
    def tracemessage(self, form):
        raise NotImplementedError

    def _dot(self, seen):
        if self in seen:
            return
        seen.add(self)
        yield '%s [label="%s", shape=box]' % (id(self), repr(self)[:50])
        if self.nextcont is not None:
            yield "%s -> %s [label=nextcont]" % (id(self), id(self.nextcont))
            for line in self.nextcont._dot(seen):
                yield line

class TraceContinuationWithModule(TraceContinuation):
    """ This class represents continuations which need
    to take care of the module system. """

    def __init__(self, engine, module, nextcont):
        TraceContinuation.__init__(self, engine, nextcont)
        self.module = module

def view(*objects):
    from dotviewer import graphclient
    content = ["digraph G{"]
    seen = set()
    for obj in objects:
        content.extend(obj._dot(seen))
    content.append("}")
    p = py.test.ensuretemp("prolog").join("temp.dot")
    p.write("\n".join(content))
    graphclient.display_dot_file(str(p))

class TraceFailureContinuation(TraceContinuation):
    """ A continuation that can represent failures. It has a .fail method that
    is called to prepare it for being used as a failure continuation.
    
    NB: a Continuation can be used both as a failure continuation and as a
    success continuation."""

    def fail(self, heap):
        """ Needs to be called to prepare the object as being used as a failure
        continuation. After fail has been called, the continuation will usually
        be activated. Particularly useful for objects that are both a regular
        and a failure continuation, to distinguish the two cases. """
        # returns (next cont, failure cont, heap)
        raise NotImplementedError("abstract base class")

    def cut(self, heap):
        """ Cut away choice points till the next correct cut delimiter.
        Slightly subtle. """
        return self

class TraceDoneContinuation(TraceFailureContinuation):
    def __init__(self, engine):
        TraceContinuation.__init__(self, engine, None)
        self.failed = False

    def activate(self, fcont, heap):
        assert 0, "unreachable"

    def fail(self, heap):
        self.failed = True
        return self, self, heap

    def is_done(self):
        return True


class TraceBodyContinuation(TraceContinuationWithModule):
    """ Represents a bit of Prolog code that is still to be called. """
    def __init__(self, engine, module, nextcont, body):
        TraceContinuationWithModule.__init__(self, engine, module, nextcont)
        self.body = body

    def activate(self, fcont, heap):
        return self.engine.call(self.body, self.module, self.nextcont, fcont, heap)

    def __repr__(self):
        return "<BodyContinuation %r>" % (self.body, )

class TraceBuiltinContinuation(TraceContinuationWithModule):
    """ Represents the call to a builtin. """
    def __init__(self, engine, module, nextcont, builtin, query):
        TraceContinuationWithModule.__init__(self, engine, module, nextcont)
        self.builtin = builtin
        self.query = query

    def activate(self, fcont, heap):
        return self.builtin.call(self.engine, self.query, self.module,
                self.nextcont, fcont, heap)

    def tracemessage(self, form):
        return None

    def __repr__(self):
        return "<BuiltinContinuation %r, %r>" % (self.builtin, self.query, )

class TraceChoiceContinuation(TraceFailureContinuation):
    """ An abstract base class for Continuations that represent a choice point,
    i.e. a point to which the execution can backtrack to."""

    def __init__(self, *args):
        TraceFailureContinuation.__init__(self, *args)
        self.undoheap = None
        self.orig_fcont = None

    #def activate(self, fcont, heap):
    #    this method needs to be structured as follows:
    #    <some code>
    #    if <has more solutions>:
    #        fcont, heap = self.prepare_more_solutions(fcont, heap)
    #    <construct cont> # must not raise UnificationFailed!
    #    return cont, fcont, heap

    def prepare_more_solutions(self, fcont, heap):
        self.undoheap = heap
        heap = heap.branch()
        self.orig_fcont = fcont
        fcont = self
        return fcont, heap
    
    def fail(self, heap):
        assert self.undoheap is not None
        heap = heap.revert_upto(self.undoheap, discard_choicepoint=True)
        return self.engine.continue_(self, self.orig_fcont, heap)

    def cut(self, heap):
        heap = self.undoheap.discard(heap)
        return self.orig_fcont.cut(heap)

    def discard(self):
        # don't propagate the discarding, as a ChoiceContinuation can both be a
        # success and a failure continuation at the same time
        pass

    def _dot(self, seen):
        if self in seen:
            return
        for line in TraceFailureContinuation._dot(self, seen):
            yield line
        seen.add(self)
        if self.orig_fcont is not None:
            yield "%s -> %s [label=orig_fcont]" % (id(self), id(self.orig_fcont))
            for line in self.orig_fcont._dot(seen):
                yield line
        if self.undoheap is not None:
            yield "%s -> %s [label=heap]" % (id(self), id(self.undoheap))
            for line in self.undoheap._dot(seen):
                yield line

class TraceUserCallContinuation(TraceChoiceContinuation):
    def __init__(self, engine, module, nextcont, query, rulechain):
        TraceChoiceContinuation.__init__(self, engine, nextcont)
        self.query = query
        self.rulechain = rulechain
        self.module = module

    def activate(self, fcont, heap):
        rulechain = jit.hint(self.rulechain, promote=True)
        rule = rulechain
        nextcont = self.nextcont
        if rule.contains_cut:
            nextcont, fcont = TraceCutDelimiter.insert_cut_delimiter(
                    self.engine, nextcont, fcont)
        query = self.query
        restchain = rulechain.find_next_applicable_rule(query)
        if restchain is not None:
            fcont, heap = self.prepare_more_solutions(fcont, heap)
            self.rulechain = restchain

        cont = TraceRuleContinuation(self.engine, self.module, nextcont, rule, query)
        return cont, fcont, heap

    def tracemessage(self, form):
        return "call", form(self.query)

    def __repr__(self):
        return "<UserCallContinuation query=%r rule=%r>" % (
                self.query, self.rulechain)

class TraceRuleContinuation(TraceContinuationWithModule):
    """ A Continuation that represents the application of a rule, i.e.:
        - standardizing apart of the rule
        - unifying the rule head with the query
        - calling the body of the rule
    """

    def __init__(self, engine, module, nextcont, rule, query):
        TraceContinuationWithModule.__init__(self, engine, module, nextcont)
        self._rule = rule
        self.query = query

    def activate(self, fcont, heap):
        nextcont = self.nextcont
        rule = jit.hint(self._rule, promote=True)
        nextcall = rule.clone_and_unify_head(heap, self.query)
        if nextcall is not None:
            return self.engine.call(nextcall, self._rule.module, nextcont, fcont, heap)
        else:
            cont = nextcont
        return cont, fcont, heap

    def __repr__(self):
        return "<RuleContinuation rule=%r query=%r>" % (self._rule, self.query)

class TraceCutScopeNotifier(TraceContinuation):
    def __init__(self, engine, nextcont):
        TraceContinuation.__init__(self, engine, nextcont)
        self.cutcell = CutCell()

    def candiscard(self):
        return not self.cutcell.discarded

    def activate(self, fcont, heap):
        self.cutcell.activated = True
        return self.nextcont, fcont, heap

    def discard(self):
        assert not self.cutcell.activated
        self.cutcell.discarded = True


class CutCell(object):
    def __init__(self):
        self.activated = False
        self.discarded = False

class TraceCutDelimiter(TraceFailureContinuation):
    def __init__(self, engine, nextcont, cutcell):
        TraceFailureContinuation.__init__(self, engine, nextcont)
        self.cutcell = cutcell

    def candiscard(self):
        return not self.cutcell.discarded

    @staticmethod
    def insert_cut_delimiter(engine, nextcont, fcont):
        if isinstance(fcont, TraceCutDelimiter):
            if fcont.cutcell.activated or fcont.cutcell.discarded:
                fcont = fcont.nextcont
                if isinstance(nextcont, TraceCutScopeNotifier) and nextcont.cutcell.discarded:
                    nextcont = nextcont.nextcont
            elif (isinstance(nextcont, TraceCutScopeNotifier) and
                    nextcont.cutcell is fcont.cutcell):
                assert not fcont.cutcell.activated
                return nextcont, fcont
        scont = TraceCutScopeNotifier(engine, nextcont)
        fcont = TraceCutDelimiter(engine, fcont, scont.cutcell)
        return scont, fcont

    def activate(self, *args):
        raise NotImplementedError("unreachable")

    def fail(self, heap):
        nextcont = self.nextcont
        assert isinstance(nextcont, TraceFailureContinuation)
        return nextcont.fail(heap)

    def cut(self, heap):
        if not self.cutcell.activated:
            return self
        nextcont = self.nextcont
        assert isinstance(nextcont, TraceFailureContinuation)
        return nextcont.cut(heap)

    def __repr__(self):
        return "<CutDelimiter activated=%r, discarded=%r>" % (self.cutcell.activated, self.cutcell.discarded)

    def _dot(self, seen):
        if self in seen:
            return
        for line in TraceFailureContinuation._dot(self, seen):
            yield line
        seen.add(self)
        yield "%s -> %s [label=nextcont]" % (id(self), id(self.nextcont))
        for line in self.nextcont._dot(seen):
            yield line


class TraceCatchingDelimiter(TraceContinuationWithModule):
    def __init__(self, engine, module, nextcont, fcont, catcher, recover, heap):
        TraceContinuationWithModule.__init__(self, engine, module, nextcont)
        self.catcher = catcher
        self.recover = recover
        self.fcont = fcont
        self.heap = heap

    def activate(self, fcont, heap):
        return self.nextcont, fcont, heap

    def _dot(self, seen):
        if self in seen:
            return
        for line in TraceContinuation._dot(self, seen):
            yield line
        if self.heap is not None:
            yield "%s -> %s [label=heap]" % (id(self), id(self.heap))
            for line in self.heap._dot(seen):
                yield line

class TraceContinueContinuation(TraceContinuation):
    def __init__(self, engine, write, cont):
        TraceContinuation.__init__(self, engine, cont)
        self.write = write

    def activate(self, fcont, heap):
        from prolog.builtin import formatting
        f = formatting.TermFormatter(self.engine, quoted=True, max_depth=20)
        tm = self.nextcont.tracemessage(f.format)
        if tm is not None:
            self.write("[%s] %s ?" % tm)
        while 1:
            if isinstance(fcont, TraceDoneContinuation):
                return TraceDoneContinuation(None), fcont, heap
            res = getch()
            if res in "\r\x04\n":
                self.write("creep\n")
                return self.nextcont, fcont, heap
            if res in "a":
                self.write("abort\n")
                return TraceDoneContinuation(None), fcont, heap
            elif res in "h?":
                self.write(tracehelptext)
            else:
                self.write('unknown action. press "h" for help\n')


