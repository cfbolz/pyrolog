import py
from prolog.interpreter.continuation import *

from prolog.interpreter.parsing import parse_query_term, get_engine
from prolog.interpreter.parsing import get_query_and_vars
from prolog.interpreter.error import UnificationFailed, UncaughtError, CatchableError
from prolog.interpreter.test.tool import collect_all, assert_true, assert_false


def test_driver():
    order = []
    done = DoneFailureContinuation(None)
    class FakeC(object):
        rule = None
        def __init__(self, next, val):
            self.next = next
            self.val = val

        def is_done(self):
            return False
        
        def activate(self, fcont, heap):
            if self.val == -1:
                raise error.UnificationFailed
            order.append(self.val)
            return self.next, fcont, heap

        def fail(self, heap):
            order.append("fail")
            return self, done, heap
        def discard(self):
            pass

    c5 = FakeC(FakeC(FakeC(FakeC(FakeC(DoneSuccessContinuation(None), 1), 2), 3), 4), 5)
    driver(c5, done, Heap())
    assert order == [5, 4, 3, 2, 1]

    order = []
    ca = FakeC(FakeC(FakeC(FakeC(FakeC(done, -1), 2), 3), 4), 5)
    driver(ca, c5, Heap())
    assert order == [5, 4, 3, 2, "fail", 5, 4, 3, 2, 1]

def test_failure_continuation():
    order = []
    h = Heap()
    done = DoneFailureContinuation(None)
    class FakeC(object):
        rule = None
        def __init__(self, next, val):
            self.next = next
            self.val = val

        def is_done(self):
            return False
        def activate(self, fcont, heap):
            if self.val == -1:
                raise error.UnificationFailed
            order.append(self.val)
            return self.next, fcont, heap

    class FakeF(FailureContinuation):
        def __init__(self, next, count):
            self.next = next
            self.count = count
            self.engine = FakeE()

        def fail(self, heap):
            if self.count:
                fcont = FakeF(self.next, self.count - 1)
                heap = heap.branch()
            else:
                fcont = DoneFailureContinuation(None)
            res = self.count
            order.append(res)
            self.count -= 1
            return self.next, fcont, heap

    class FakeE(object):
        pass

    ca = FakeF(FakeC(FakeC(DoneSuccessContinuation(None), -1), 'c'), 10)
    py.test.raises(UnificationFailed, driver, FakeC(DoneSuccessContinuation(None), -1), ca, h)
    assert order == [10, 'c', 9, 'c', 8, 'c', 7, 'c', 6, 'c', 5, 'c', 4, 'c',
                     3, 'c', 2, 'c', 1, 'c', 0, 'c']

def test_full():
    from prolog.interpreter.term import Var, Atom, Term
    all = []
    e = Engine()
    class CollectContinuation(object):
        rule = None
        module = e.modulewrapper.user_module
        def is_done(self):
            return False
        def discard(self):
            pass
        def activate(self, fcont, heap):
            all.append(query.getvalue(heap))
            raise error.UnificationFailed
    e.add_rule(Callable.build("f", [Callable.build("x")]), True)
    e.add_rule(Callable.build("f", [Callable.build("y")]), True)
    e.add_rule(Callable.build("g", [Callable.build("a")]), True)
    e.add_rule(Callable.build("g", [Callable.build("b")]), True)
            
    query = Callable.build(",", [Callable.build("f", [Var()]), Callable.build("g", [Var()])])
    py.test.raises(error.UnificationFailed,
                   e.run_query, query, e.modulewrapper.user_module, CollectContinuation())
    assert all[0].argument_at(0).argument_at(0).name()== "x"
    assert all[0].argument_at(1).argument_at(0).name()== "a"
    assert all[1].argument_at(0).argument_at(0).name()== "x"
    assert all[1].argument_at(1).argument_at(0).name()== "b"
    assert all[2].argument_at(0).argument_at(0).name()== "y"
    assert all[2].argument_at(1).argument_at(0).name()== "a"
    assert all[3].argument_at(0).argument_at(0).name()== "y"
    assert all[3].argument_at(1).argument_at(0).name()== "b"


def test_cut_not_reached():
    class CheckContinuation(Continuation):
        def __init__(self):
            self.nextcont = None
            self.module = e.modulewrapper.user_module
        def is_done(self):
            return False
        def activate(self, fcont, heap):
            assert fcont.is_done()
            return DoneSuccessContinuation(e), DoneFailureContinuation(e), heap
    e = get_engine("""
        g(X, Y) :- X > 0, !, Y = a.
        g(_, b).
    """)
    e.run(parse_query_term("g(-1, Y), Y == b, g(1, Z), Z == a."), 
            e.modulewrapper.user_module, CheckContinuation())

# ___________________________________________________________________
# integration tests

def test_trivial():
    e = get_engine("""
        f(a).
    """)
    m = e.modulewrapper
    t, vars = get_query_and_vars("f(X).")
    e.run(t, m.user_module)
    assert vars['X'].dereference(None).name()== "a"

def test_and():
    e = get_engine("""
        g(a, a).
        g(a, b).
        g(b, c).
        f(X, Z) :- g(X, Y), g(Y, Z).
    """)
    m = e.modulewrapper
    e.run(parse_query_term("f(a, c)."), m.user_module)
    t, vars = get_query_and_vars("f(X, c).")
    e.run(t, m.user_module)
    assert vars['X'].dereference(None).name()== "a"

def test_and_long():
    e = get_engine("""
        f(x). f(y). f(z).
        g(a). g(b). g(c).
        h(d). h(e). h(f).
        f(X, Y, Z) :- f(X), g(Y), h(Z).
    """)
    heaps = collect_all(e, "f(X, Y, Z).")
    assert len(heaps) == 27  

def test_numeral():
    e = get_engine("""
        num(0).
        num(succ(X)) :- num(X).
        add(X, 0, X).
        add(X, succ(Y), Z) :- add(succ(X), Y, Z).
        mul(X, 0, 0).
        mul(X, succ(0), X).
        mul(X, succ(Y), Z) :- mul(X, Y, A), add(A, X, Z).
        factorial(0, succ(0)).
        factorial(succ(X), Y) :- factorial(X, Z), mul(Z, succ(X), Y).
    """)
    m = e.modulewrapper
    def nstr(n):
        if n == 0:
            return "0"
        return "succ(%s)" % nstr(n - 1)
    e.run(parse_query_term("num(0)."), m.user_module)
    e.run(parse_query_term("num(succ(0))."), m.user_module)
    t, vars = get_query_and_vars("num(X).")
    e.run(t, m.user_module)
    assert vars['X'].dereference(None).num == 0
    e.run(parse_query_term("add(0, 0, 0)."), m.user_module)
    py.test.raises(UnificationFailed, e.run, parse_query_term("""
        add(0, 0, succ(0))."""), m.user_module)
    e.run(parse_query_term("add(succ(0), succ(0), succ(succ(0)))."), m.user_module)
    e.run(parse_query_term("mul(succ(0), 0, 0)."), m.user_module)
    e.run(parse_query_term("mul(succ(succ(0)), succ(0), succ(succ(0)))."), m.user_module)
    e.run(parse_query_term("mul(succ(succ(0)), succ(succ(0)), succ(succ(succ(succ(0)))))."), m.user_module)
    e.run(parse_query_term("factorial(0, succ(0))."), m.user_module)
    e.run(parse_query_term("factorial(succ(0), succ(0))."), m.user_module)
    e.run(parse_query_term("factorial(%s, %s)." % (nstr(5), nstr(120))), m.user_module)

def test_or_backtrack():
    e = get_engine("""
        a(a).
        b(b).
        g(a, b).
        g(a, a).
        f(X, Y, Z) :- (g(X, Z); g(X, Z); g(Z, Y)), a(Z).
        """)
    t, vars = get_query_and_vars("f(a, b, Z).")
    e.run(t, e.modulewrapper.user_module)
    assert vars['Z'].dereference(None).name()== "a"
    f = collect_all(e, "X = 1; X = 2.")
    assert len(f) == 2

def test_backtrack_to_same_choice_point():
    e = get_engine("""
        a(a).
        b(b).
        start(Z) :- Z = X, f(X, b), X == b, Z == b.
        f(X, Y) :- a(Y).
        f(X, Y) :- X = a, a(Y).
        f(X, Y) :- X = b, b(Y).
    """)
    assert_true("start(Z).", e)

def test_collect_all():
    e = get_engine("""
        g(a).
        g(b).
        g(c).
    """)
    heaps = collect_all(e, "g(X).")
    assert len(heaps) == 3
    assert heaps[0]['X'].name()== "a"
    assert heaps[1]['X'].name()== "b"
    assert heaps[2]['X'].name()== "c"

def test_lists():
    e = get_engine("""
        nrev([],[]).
        nrev([X|Y],Z) :- nrev(Y,Z1),
                         append(Z1,[X],Z).

        append([],L,L).
        append([X|Y],L,[X|Z]) :- append(Y,L,Z).
    """)
    e.run(parse_query_term("append(%s, %s, X)." % (range(30), range(10))),
            e.modulewrapper.user_module)
    return
    e.run(parse_query_term("nrev(%s, X)." % (range(15), )))
    e.run(parse_query_term("nrev(%s, %s)." % (range(8), range(7, -1, -1))))

def test_indexing():
    # this test is quite a lot faster if indexing works properly. hrmrm
    e = get_engine("g(a, b, c, d, e, f, g, h, i, j, k, l). " +
            "".join(["f(%s, g(%s)) :- g(A, B, C, D, E, F, G, H, I ,J, K, l). "
                      % (chr(i), chr(i + 1))
                                for i in range(97, 122)]))
    t = parse_query_term("f(x, g(y)).")
    for i in range(200):
        e.run(t, e.modulewrapper.user_module)
    t = parse_query_term("f(x, g(y, a)).")
    for i in range(200):
        py.test.raises(UnificationFailed, e.run, t, e.modulewrapper.user_module)

def test_indexing2():
    e = get_engine("""
        mother(o, j).
        mother(o, m).
        mother(o, b).

        sibling(X, Y) :- mother(Z, X), mother(Z, Y).
    """)
    heaps = collect_all(e, "sibling(m, X).")
    assert len(heaps) == 3

@py.test.mark.xfail
def test_runstring():
    e = get_engine("foo(a, c).")
    e.runstring("""
        :- op(450, xfy, foo).
        a foo b.
        b foo X :- a foo X.
    """)
    assert_true("foo(a, b).", e)

def test_call_atom():
    e = get_engine("""
        test(a).
        test :- test(_).
    """)
    assert_true("test.", e)


def test_metainterp():
    e = get_engine("""
        run(X) :- solve([X]).
        solve([]).
        solve([A | T]) :-
            my_pred(A, T, T1),
            solve(T1).

        my_pred(app([], X, X), T, T).
        my_pred(app([H | T1], T2, [H | T3]), T, [app(T1, T2, T3) | T]).

    """)
    assert_true("run(app([1, 2, 3, 4], [5, 6], X)), X == [1, 2, 3, 4, 5, 6].", e)

# ___________________________________________________________________
# Trace tests

def test_trace():
    e = get_engine("")
    assert e.tracewrapper.tracing == False
    e.run(parse_query_term("trace."), e.modulewrapper.user_module, DoneSuccessContinuation(e))
    assert e.tracewrapper.tracing == True
    e.run(parse_query_term("notrace."), e.modulewrapper.user_module, DoneSuccessContinuation(e))
    assert e.tracewrapper.tracing == False

def test_trace_tracing():
    e = get_engine("")
    order = []
    def w(s):
        order.append(s)
    def g():
        return "\n"
    e.tracewrapper.write = w
    e.tracewrapper.getch = g
    assert_true("trace, tracing.", e)
    assert_false("notrace, tracing.", e)
    assert_true("trace,tracing,notrace.",e)
    assert order == []

def test_trace_fact():
    e = get_engine("""
       f(1).
       f(2).
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "\n"

    e.tracewrapper.write = w
    e.tracewrapper.getch = g
    e.run(parse_query_term("trace, f(1)."), e.modulewrapper.user_module)
    assert order == ["Call: (1) f(1) ?", "creep\n", "Exit: (1) f(1) ?", "creep\n"]

    order = []
    e.run(parse_query_term("trace, f(2)."), e.modulewrapper.user_module)
    assert order == ["Call: (1) f(2) ?", "creep\n", "Exit: (1) f(2) ?", "creep\n"]
    
@py.test.mark.xfail
def test_trace_fact_fail():
    e = get_engine("""
       f(1).
       f(2).
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "\n"

    e.tracewrapper.write = w
    e.tracewrapper.getch = g

    t = parse_query_term("trace, f(3).")
    # XXX wrap BodyContinuation to display trace
    py.test.raises(UnificationFailed, e.run, t, e.modulewrapper.user_module)
    assert order == ["Call: (1) f(3) ?", "creep\n", "Fail: (1) f(3) ?", "creep\n"]

def test_trace_success():
    e = get_engine("""
       f(X) :- X = 1.
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "\n"

    e.tracewrapper.write = w
    e.tracewrapper.getch = g
    e.run(parse_query_term("trace, f(1)."), e.modulewrapper.user_module)
    assert order == ["Call: (1) f(1) ?", "creep\n", "Call: (2) 1=1 ?", "creep\n", "Exit: (2) 1=1 ?",
            "creep\n", "Exit: (1) f(1) ?", "creep\n"]

def test_trace_simple_fail():
    e = get_engine("""
        f(X) :- X = 1.
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "\n"

    e.tracewrapper.write = w
    e.tracewrapper.getch = g
    t = parse_query_term("trace, f(2).")
    py.test.raises(UnificationFailed, e.run, t, e.modulewrapper.user_module)
    #e.run(parse_query_term("trace, f(2)."), e.modulewrapper.user_module)

    assert order == ["Call: (1) f(2) ?","creep\n","Call: (2) 2=1 ?","creep\n","Fail: (2) 2=1 ?",
            "creep\n","Fail: (1) f(2) ?","creep\n"]

def test_trace_fail_success():
    e = get_engine("""
        f(X) :- X = 1 ; X = 2.
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "\n"

    e.tracewrapper.write = w
    e.tracewrapper.getch = g
    e.run(parse_query_term("trace, f(2)."), e.modulewrapper.user_module)

    assert order == ["Call: (1) f(2) ?","creep\n","Call: (2) 2=1 ?","creep\n","Fail: (2) 2=1 ?","creep\n",
            "Call: (2) 2=2 ?","creep\n","Exit: (2) 2=2 ?","creep\n","Exit: (1) f(2) ?","creep\n"]

def test_trace_fail_redo():
    e = get_engine("""
        f(X) :- X = 1 ; X = 2.
        f(X) :- X = x.
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "\n"

    e.tracewrapper.write = w
    e.tracewrapper.getch = g
    e.run(parse_query_term("trace, f(x)."), e.modulewrapper.user_module)

    assert order == ["Call: (1) f(x) ?","creep\n","Call: (2) x=1 ?","creep\n","Fail: (2) x=1 ?","creep\n",
            "Call: (2) x=2 ?","creep\n","Fail: (2) x=2 ?","creep\n","Redo: (1) f(x) ?",
            "creep\n","Call: (2) x=x ?","creep\n","Exit: (2) x=x ?","creep\n","Exit: (1) f(x) ?","creep\n"]

def test_trace_redo_fail():
    e = get_engine("""
        f(X) :- X = 1 ; X = 2.
        f(X) :- X = x.
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "\n"

    e.tracewrapper.write = w
    e.tracewrapper.getch = g
    t = parse_query_term("trace, f(a).")
    py.test.raises(UnificationFailed, e.run, t, e.modulewrapper.user_module)

    assert order == ["Call: (1) f(a) ?","creep\n","Call: (2) a=1 ?","creep\n","Fail: (2) a=1 ?","creep\n",
            "Call: (2) a=2 ?","creep\n","Fail: (2) a=2 ?","creep\n","Redo: (1) f(a) ?",
            "creep\n","Call: (2) a=x ?","creep\n","Fail: (2) a=x ?","creep\n","Fail: (1) f(a) ?","creep\n"]

def test_trace_complex():
    e = get_engine("""
        f(X,Y) :- g(X), h(X,Y).
        g(X) :- X =.. ['.',1,[]].
        h([],[]).
        h([H|R], [H|R2]) :- h(R,R2).
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "\n"

    e.tracewrapper.write = w
    e.tracewrapper.getch = g
    e.run(parse_query_term("trace, f(X,Y)."), e.modulewrapper.user_module)
    c = "creep\n"
    # XXX SWI: [Exit] [1]=..['.', 1, 1[]] ? dereference
    # XXX SWI: h([], _G0) ? global variable numerization
    assert order == ["Call: (1) f(_G0, _G1) ?",c,"Call: (2) g(_G0) ?",c,
            "Call: (3) _G0=..['.', 1, []] ?",c,"Exit: (3) _G0=..['.', 1, []] ?",
            c,"Exit: (2) g(_G0) ?",c,"Call: (2) h(_G0, _G1) ?",c,"Call: (3) h([], _G0) ?",
            c,"Exit: (3) h([], _G0) ?",c,"Exit: (2) h(_G0, _G1) ?",c,"Exit: (1) f(_G0, _G1) ?",c]

def test_trace_skip():
    e = get_engine("""
        f(a).
        f(b).
        f(X) :- X=1;X=2.
        f(X) :- X=x.
    """)
    order = []
    def w(s):
        order.append(s)
    def gen():
        # f(a)
        yield "s"
        yield "\n"

        # f(b)
        yield "s"
        yield "\n"

        # f(2)
        for i in ["s", "\n"]:
            yield i

        # f(x)
        for i in ["\n","\n","\n","\n","\n","s","\n"]:
            yield i

        # f(abc)
        yield "s"
        yield "\n"
    gengetch = gen()
    def g():
        return gengetch.next()

    e.tracewrapper.write = w
    e.tracewrapper.getch = g
    try:
        e.run(parse_query_term("trace, f(a)."), e.modulewrapper.user_module)
    except StopIteration:
        pass
    assert order == ["Call: (1) f(a) ?", "skip\n", "Exit: (1) f(a) ?", "creep\n"]

    order = []
    try:
        e.run(parse_query_term("trace, f(b)."), e.modulewrapper.user_module)
    except StopIteration:
        pass
    assert order == ["Call: (1) f(b) ?", "skip\n", "Exit: (1) f(b) ?", "creep\n"]

    order = []
    try:
        e.run(parse_query_term("trace, f(2)."), e.modulewrapper.user_module)
    except StopIteration:
        pass
    assert order == ["Call: (1) f(2) ?", "skip\n", "Exit: (1) f(2) ?", "creep\n"]

    order = []
    try:
        e.run(parse_query_term("trace, f(x)."), e.modulewrapper.user_module)
    except StopIteration:
        pass
    assert order == ["Call: (1) f(x) ?","creep\n","Call: (2) x=1 ?","creep\n","Fail: (2) x=1 ?","creep\n",
            "Call: (2) x=2 ?","creep\n","Fail: (2) x=2 ?","creep\n","Redo: (1) f(x) ?","skip\n",
            "Exit: (1) f(x) ?","creep\n"]

    order = []
    t = parse_query_term("trace, f(abc).")
    try:
        py.test.raises(UnificationFailed, e.run, t, e.modulewrapper.user_module)
    except StopIteration:
        pass
    assert order == ["Call: (1) f(abc) ?", "skip\n", "Fail: (1) f(abc) ?", "creep\n"]

def test_trace_write_print():
    e = get_engine("""
    f(X) :- X=a;X=b.
    """)
    order = []
    def w(s):
        order.append(s)
    def gen():
        for i in ["\n","w","\n","w","\n","p","\n"]:
            yield i

    gengetch = gen()
    def g():
        return gengetch.next()

    e.tracewrapper.write = w
    e.tracewrapper.getch = g

    try:
        e.run(parse_query_term("trace, f(a)."), e.modulewrapper.user_module)
    except StopIteration:
        pass

    assert order == ["Call: (1) f(a) ?","creep\n","Call: (2) a=a ?","write\n","Call: (2) a=a ?","creep\n",
            "Exit: (2) a=a ?","write\n","Exit: (2) a=a ?","creep\n","Exit: (1) f(a) ?",
            "print\n","Exit: (1) f(a) ?","creep\n"]

def test_trace_goals():
    e = get_engine("""
    append([], X, X).
    append([H|T], X, [H|Y]) :-
        append(T, X, Y).
    """)
    order = []
    def w(s):
        order.append(s)
    def gen():
        for i in 6*["g","\n"]:
            yield i
    gengetch = gen()
    def g():
        return gengetch.next()
    e.tracewrapper.write = w
    e.tracewrapper.getch = g

    try:
        e.run(parse_query_term("trace, append([1,2],[3,4],X)."), e.modulewrapper.user_module)
    except StopIteration:
        pass

    c = "creep\n"
    g1 = "    [1] append([1, 2], [3, 4], _G0)\n"
    g2 = "    [2] append([2], [3, 4], _G0)\n"
    g3 = "    [3] append([], [3, 4], _G0)\n"
    assert order == ["Call: (1) append([1, 2], [3, 4], _G0) ?","goals\n",g1,
            "Call: (1) append([1, 2], [3, 4], _G0) ?",c,
            "Call: (2) append([2], [3, 4], _G0) ?","goals\n",g2,g1,"Call: (2) append([2], [3, 4], _G0) ?",c,
            "Call: (3) append([], [3, 4], _G0) ?","goals\n",g3,g2,g1,"Call: (3) append([], [3, 4], _G0) ?",c,
            "Exit: (3) append([], [3, 4], _G0) ?","goals\n",g3,g2,g1,"Exit: (3) append([], [3, 4], _G0) ?",c,
            "Exit: (2) append([2], [3, 4], _G0) ?","goals\n",g2,g1,"Exit: (2) append([2], [3, 4], _G0) ?",c,
            "Exit: (1) append([1, 2], [3, 4], _G0) ?","goals\n",g1,"Exit: (1) append([1, 2], [3, 4], _G0) ?",c]

def test_trace_goals_fail():
    e = get_engine("""
    append([], X, X).
    append([H|T], X, [H|Y]) :-
        append(T, X, Y).
    """)
    order = []
    def w(s):
        order.append(s)
    def gen():
        for i in 6*["g","\n"]:
            yield i
    gengetch = gen()
    def g():
        return gengetch.next()
    e.tracewrapper.write = w
    e.tracewrapper.getch = g

    t = parse_query_term("trace, append([1],[2],[1,2,3]).")
    try:
        py.test.raises(UnificationFailed, e.run, t, e.modulewrapper.user_module)
    except StopIteration:
        pass

    c = "creep\n"
    g1 = "    [1] append([1], [2], [1, 2, 3])\n"
    g2 = "    [2] append([], [2], [2, 3])\n"
    assert order == ["Call: (1) append([1], [2], [1, 2, 3]) ?","goals\n",g1,
            "Call: (1) append([1], [2], [1, 2, 3]) ?",c,
            "Call: (2) append([], [2], [2, 3]) ?","goals\n",g2,g1,"Call: (2) append([], [2], [2, 3]) ?",c,
            "Fail: (2) append([], [2], [2, 3]) ?","goals\n",g2,g1,"Fail: (2) append([], [2], [2, 3]) ?",c,
            "Fail: (1) append([1], [2], [1, 2, 3]) ?","goals\n",g1,"Fail: (1) append([1], [2], [1, 2, 3]) ?",c]

def test_trace_goals_redo():
    e = get_engine("""
    f(X) :- X=1;X=2.
    f(X) :- X=x.
    """)
    order = []
    def w(s):
        order.append(s)
    def gen():
        for i in ["\n","\n","\n","\n","\n"] + 4*["g","\n"]:
            yield i
    gengetch = gen()
    def g():
        return gengetch.next()
    e.tracewrapper.write = w
    e.tracewrapper.getch = g

    try:
        e.run(parse_query_term("trace, f(x)."), e.modulewrapper.user_module)
    except StopIteration:
        pass

    c = "creep\n"
    assert order[10:] == ["Redo: (1) f(x) ?","goals\n","    [1] f(x)\n","Redo: (1) f(x) ?",c,
            "Call: (2) x=x ?","goals\n","    [2] x=x\n","    [1] f(x)\n","Call: (2) x=x ?",c,
            "Exit: (2) x=x ?","goals\n","    [2] x=x\n","    [1] f(x)\n","Exit: (2) x=x ?",c,
            "Exit: (1) f(x) ?","goals\n","    [1] f(x)\n","Exit: (1) f(x) ?",c]

def test_trace_leap():
    e = get_engine("""
    f(X) :- X=1;X=2.

    llength([],0).
    llength([_|T], X) :-
        llength(T, X1),
        X is X1 + 1.
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "l"
    e.tracewrapper.write = w
    e.tracewrapper.getch = g

    e.run(parse_query_term("trace,f(2)."), e.modulewrapper.user_module)
    assert order == ["Call: (1) f(2) ?","leap\n"]
    assert e.tracewrapper.tracing == False

    order = []
    e.run(parse_query_term("trace,llength([1,2,3],3)."), e.modulewrapper.user_module)
    assert order == ["Call: (1) llength([1, 2, 3], 3) ?", "leap\n"]
    assert e.tracewrapper.tracing == False

@py.test.mark.xfail
def test_trace_leap2():
    e = get_engine("""
    llength([],0).
    llength([_|T], X) :-
        llength(T, X1),
        trace,
        X is X1 + 1.
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "l"
    e.tracewrapper.write = w
    e.tracewrapper.getch = g

    e.run(parse_query_term("trace, llength([1], X)."), e.modulewrapper.user_module)
    # XXX depth will start from 0 every "trace"
    assert order == ["Call: (1) llength([1], _G0) ?","leap\n","Call: (2) _G0is_G1+1 ?","leap\n"]
    assert e.tracewrapper.tracing == False

def test_trace_failopt():
    e = get_engine("""
    list([]).
    list([_|R]) :- list(R).

    f(X) :- X=1;X=2.
    f(X) :- X=x.
    """)
    order = []
    def w(s):
        order.append(s)
    def gen():
        for i in ["\n","f","f"] + ["\n","f","\n","f","f","f","\n"]:
            yield i
    gengetch = gen()
    def g():
        return gengetch.next()
    e.tracewrapper.write = w
    e.tracewrapper.getch = g
    try:
        py.test.raises(UnificationFailed, e.run, parse_query_term("trace,list([1,2,3])."),
                e.modulewrapper.user_module)
    except StopIteration:
        pass 
    # XXX decide if fail-forced level should be outputted; currently: no
    assert order == ["Call: (1) list([1, 2, 3]) ?","creep\n","Call: (2) list([2, 3]) ?","fail\n",
            "Fail: (1) list([1, 2, 3]) ?","fail\n"]

    order = []
    try:
        py.test.raises(UnificationFailed, e.run, parse_query_term("trace, f(x)."), e.modulewrapper.user_module)
    except StopIteration:
        pass
    assert order == ["Call: (1) f(x) ?","creep\n","Call: (2) x=1 ?","fail\n","Call: (2) x=2 ?","creep\n",
            "Fail: (2) x=2 ?","fail\n","Redo: (1) f(x) ?","fail\n"]

def test_trace_failopt2():
    e = get_engine("""
    f(X) :- X=1;X=2.
    f(X) :- X=x.
    f(X) :- X=a;X=b.
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "f"
    e.tracewrapper.write = w
    e.tracewrapper.getch = g

    py.test.raises(UnificationFailed, e.run, parse_query_term("trace, f(x)."), e.modulewrapper.user_module)
    assert order == ["Call: (1) f(x) ?","fail\n"]

def test_trace_retry():
    e = get_engine("""
    f(X) :- X=1;X=2.
    f(X) :- X=x.
    """)
    order = []
    def w(s):
        order.append(s)
    def gen():
        for i in ["\n","r","r","\n","\n","\n","\n","\n"] + ["\n","\n","\n","\n","\n","r","s","\n"]:
            yield i
        for i in ["\n"] * 8 + ["r","s","\n"]:
            yield i
    gengetch = gen()
    def g():
        return gengetch.next()
    e.tracewrapper.write = w
    e.tracewrapper.getch = g

    try:
        e.run(parse_query_term("trace, f(2)."), e.modulewrapper.user_module)
    except StopIteration:
        pass
    assert order == ["Call: (1) f(2) ?","creep\n","Call: (2) 2=1 ?","retry\n","Can't retry at this point\n",
            "Fail: (2) 2=1 ?","retry\n","[retry]\n","Call: (2) 2=1 ?","creep\n","Fail: (2) 2=1 ?","creep\n",
            "Call: (2) 2=2 ?","creep\n","Exit: (2) 2=2 ?","creep\n","Exit: (1) f(2) ?","creep\n"]

    order = []
    try:
        e.run(parse_query_term("trace, f(x)."), e.modulewrapper.user_module)
    except StopIteration:
        pass
    assert order == ["Call: (1) f(x) ?","creep\n","Call: (2) x=1 ?","creep\n","Fail: (2) x=1 ?","creep\n",
            "Call: (2) x=2 ?","creep\n","Fail: (2) x=2 ?","creep\n","Redo: (1) f(x) ?","retry\n","[retry]\n",
            "Call: (1) f(x) ?","skip\n","Exit: (1) f(x) ?","creep\n"]

    order = []
    try:
        e.run(parse_query_term("trace, f(x)."), e.modulewrapper.user_module)
    except StopIteration:
        pass
    assert order == ["Call: (1) f(x) ?","creep\n","Call: (2) x=1 ?","creep\n","Fail: (2) x=1 ?","creep\n",
            "Call: (2) x=2 ?","creep\n","Fail: (2) x=2 ?","creep\n","Redo: (1) f(x) ?","creep\n",
            "Call: (2) x=x ?","creep\n","Exit: (2) x=x ?","creep\n","Exit: (1) f(x) ?","retry\n",
            "[retry]\n","Call: (1) f(x) ?","skip\n","Exit: (1) f(x) ?","creep\n"]

#XXX BodyContinuation must be wrapped to trace non-existing predicate Calls
@py.test.mark.xfail
def test_trace_exception():
    e = get_engine("""
    err2(X) :- err1(X).
    err1(X) :- err(X).
    err(X) :- X < 1, not_exists(X).
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "\n"
    e.tracewrapper.write = w
    e.tracewrapper.getch = g

    py.test.raises(UncaughtError, e.run, parse_query_term("trace, err2(0)."), e.modulewrapper.user_module)
    assert order == ["Call: (1) err2(0) ?","creep\n","Call: (2) err1(0) ?","creep\n","Call: (3) err(0) ?",
            "creep\n","Call: (4) 0<1 ?","creep\n","Exit: (4) 0<1 ?","creep\n","Call: (4) not_exists(0) ?",
            "creep\n","Error: err/1: Undefined procedure: not_exists/1\n","Exception: (3) err(0) ?","creep\n",
            "Exception: (2) err1(0) ?","creep\n","Exception: (1) err2(0) ?","creep\n"]

def test_trace_leash():
    e = get_engine("""
    f(X) :- X = 1; X = 2.
    f(X) :- X = x.
    """)
    order = []
    def w(s):
        order.append(s)
    def g():
        return "\n"
    e.tracewrapper.write = w
    e.tracewrapper.getch = g

    try:
        e.run(parse_query_term("leash(X)."), e.modulewrapper.user_module)
    except UncaughtError, err:
        assert err.term.argument_at(0).name() == "instantiation_error"

    try:
        e.run(parse_query_term("leash([foo])."), e.modulewrapper.user_module)
    except UncaughtError, err:
        assert err.term.argument_at(0).name() == "domain_error"

    try:
        e.run(parse_query_term("leash([call,foo])."), e.modulewrapper.user_module)
    except UncaughtError, err:
        assert err.term.argument_at(0).name() == "domain_error"

    e.run(parse_query_term("leash([call,exit])."), e.modulewrapper.user_module)
    e.run(parse_query_term("leash([call,exit]), trace, f(x)."), e.modulewrapper.user_module)
    assert order == ["Call: (1) f(x) ?","creep\n","Call: (2) x=1 ?","creep\n","Fail: (2) x=1 ?",
            "Call: (2) x=2 ?","creep\n","Fail: (2) x=2 ?","Redo: (1) f(x) ?","Call: (2) x=x ?",
            "creep\n","Exit: (2) x=x ?","creep\n","Exit: (1) f(x) ?","creep\n"]

    order = []
    e.run(parse_query_term("leash([]), trace, f(x)."), e.modulewrapper.user_module)
    assert order == ["Call: (1) f(x) ?","Call: (2) x=1 ?","Fail: (2) x=1 ?","Call: (2) x=2 ?",
            "Fail: (2) x=2 ?","Redo: (1) f(x) ?","Call: (2) x=x ?","Exit: (2) x=x ?",
            "Exit: (1) f(x) ?"]
