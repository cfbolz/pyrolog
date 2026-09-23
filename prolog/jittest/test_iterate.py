from prolog.jittest.support import BaseTestPyrologC

class TestIterate(BaseTestPyrologC):
    def test_call(self):
        code = """
        iterate_call(X) :- c(X, c).
        c(0, _).
        c(X, Pred) :-
            Y is X - 1, C =.. [Pred, Y, Pred], call(C).
        """
        log = self.run_and_check(code, "iterate_call(10000).")
        loop, = log.filter_loops("c/2")
        assert loop.match("""
            guard_not_invalidated(descr=...)
            i24 = int_sub_ovf(i16, 1)
            guard_no_overflow(descr=...)
            i25 = int_is_zero(i24)
            guard_false(i25, descr=...)
            jump(p4, p2, i24, p8, p1, descr=...)
        """)

    def test_cut(self):
        code = """
            iterate_cut(0) :- !.
            iterate_cut(X) :- Y is X - 1, !, iterate_cut(Y).
            iterate_cut(X) :- Y is X - 2, iterate_cut(Y).
        """
        log = self.run_and_check(code, "iterate_cut(10000), findall(done, iterate_cut(3), Results).")
        assert "Results = [done]" in log.result
        loop, = log.filter_loops("iterate_cut/1")
        assert loop.match("""
            guard_not_invalidated(descr=...)
            i43 = int_sub_ovf(i14, 1)
            guard_no_overflow(descr=...)
            i44 = getfield_gc_i(p2, descr=<FieldS prolog.interpreter.heap.Heap.inst_i .*>)
            setfield_gc(p2, 1, descr=<FieldU prolog.interpreter.heap.Heap.inst_discarded .*>)
            i47 = int_lt(i44, 6)
            guard_true(i47, descr=...)
            i49 = int_is_zero(i44)
            guard_true(i49, descr=...)
            p50 = getfield_gc_r(p2, descr=<FieldP prolog.interpreter.heap.Heap.inst_prev .*>)
            setfield_gc(p2, -1, descr=<FieldS prolog.interpreter.heap.Heap.inst_i .*>)
            setfield_gc(p2, ConstPtr(null), descr=<FieldP prolog.interpreter.heap.Heap.inst_trail_var .*>)
            setfield_gc(p2, ConstPtr(null), descr=<FieldP prolog.interpreter.heap.Heap.inst_trail_binding .*>)
            guard_class(p16, #, descr=...)
            i55 = instance_ptr_eq(p16, p41)
            guard_true(i55, descr=...)
            i56 = int_is_zero(i43)
            guard_false(i56, descr=...)
            p57 = new_with_vtable(descr=...)
            setfield_gc(p2, p57, descr=<FieldP prolog.interpreter.heap.Heap.inst_prev .*>)
            setfield_gc(p57, ConstPtr(null), descr=<FieldP prolog.interpreter.heap.Heap.inst_hook .*>)
            setfield_gc(p57, ConstPtr(null), descr=<FieldP prolog.interpreter.heap.Heap.inst_trail_attrs .*>)
            setfield_gc(p57, 0, descr=<FieldU prolog.interpreter.heap.Heap.inst_discarded .*>)
            setfield_gc(p57, 0, descr=<FieldS prolog.interpreter.heap.Heap.inst_i .*>)
            setfield_gc(p57, p50, descr=<FieldP prolog.interpreter.heap.Heap.inst_prev .*>)
            setfield_gc(p57, ConstPtr(ptr62), descr=<FieldP prolog.interpreter.heap.Heap.inst_trail_var .*>)
            setfield_gc(p57, ConstPtr(ptr63), descr=<FieldP prolog.interpreter.heap.Heap.inst_trail_binding .*>)
            jump(p4, p57, i43, p41, p41, descr=...)
        """)

    def test_failure_driven(self):
        code = """
            g(X, Y, Out) :- Out is X - Y.
            g(X, Y, Out) :- Y > 0, Y0 is Y - 1, g(X, Y0, Out).
            iterate_failure(X) :- g(X, X, A), fail.
            iterate_failure(_).
        """
        log = self.run_and_check(code, "iterate_failure(10000), findall(A, g(5, 5, A), Results).")
        assert "Results = [0, 1, 2, 3, 4, 5]" in log.result
        loop, = log.filter_loops("g/3")
        assert loop.match("""
            guard_not_invalidated(descr=...)
            guard_class(p64, ConstClass(Number), descr=...)
            i80 = getfield_gc_i(p64, descr=<FieldS prolog.interpreter.term.Number.inst_num .* pure>)
            i81 = int_sub_ovf(i80, i78)
            guard_no_overflow(descr=...)
            guard_class(p66, #, descr=...)
            p83 = getfield_gc_r(p66, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            guard_isnull(p83, descr=...)
            p84 = getfield_gc_r(p66, descr=<FieldP prolog.interpreter.term.Var.inst_created_after_choice_point .*>)
            guard_nonnull(p84, descr=...)
            i85 = getfield_gc_i(p84, descr=<FieldU prolog.interpreter.heap.Heap.inst_discarded .*>)
            guard_false(i85, descr=...)
            guard_class(p68, #, descr=...)
            p87 = getfield_gc_r(p68, descr=<FieldP prolog.interpreter.continuation.ContinuationWithRule.inst_rule .*>)
            guard_value(p87, ConstPtr(ptr88), descr=...)
            p89 = getfield_gc_r(p68, descr=<FieldP prolog.interpreter.continuation.BodyContinuation.inst_body .*>)
            p90 = getfield_gc_r(p68, descr=<FieldP prolog.interpreter.continuation.Continuation.inst_nextcont .*>)
            guard_nonnull_class(p89, ConstClass(Atom), descr=...)
            p92 = getfield_gc_r(p89, descr=<FieldP prolog.interpreter.term.Atom.inst__signature .* pure>)
            guard_value(p92, ConstPtr(ptr93), descr=...)
            i95 = int_gt(i78, 0)
            guard_true(i95, descr=...)
            i97 = int_add(i78, -1)
            jump(p68, p66, p64, p44, i97, p69, descr=...)
        """)

    def test_ifthenelse(self):
        code = """
            equal(0, 0). equal(X, X).
            iterate_if(X) :- equal(X, 0) -> true ;
                             Y is X - 1, iterate_if(Y).
        """
        log = self.run_and_check(code, "iterate_if(10000).")
        loop, = log.filter_loops("iterate_if/1")
        assert loop.match("""
            guard_not_invalidated(descr=...)
            i20 = int_is_zero(i19)
            guard_false(i20, descr=...)
            i21 = getfield_gc_i(p2, descr=<FieldU prolog.interpreter.heap.Heap.inst_discarded .*>)
            guard_false(i21, descr=...)
            i23 = int_sub_ovf(i19, 1)
            guard_no_overflow(descr=...)
            jump(p4, p2, i23, p1, descr=...)
        """)
