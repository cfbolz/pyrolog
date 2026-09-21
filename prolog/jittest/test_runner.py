from prolog.jittest.support import BaseTestPyrologC


class TestRunPyrologC(BaseTestPyrologC):

    def test_run_function(self):
        code = """
        length(L, O) :- length(L, 0, O).
        length([], O, O).
        length([_ | T], I, O) :- I1 is I + 1, length(T, I1, O).
        """
        log = self.run(code, "append([1, 2, 3], [3, 4, 5], X), length(X, Y).")
        assert "Y = 6" in log.result

    def test_check_logs(self):
        code = """
        loop(0).
        loop(X) :- X > 0, X0 is X - 1, loop(X0).
        """
        log = self.run_and_check(code, "loop(3000).")
        loop, = log.filter_loops()
        assert loop.match("""
            guard_not_invalidated(descr=...)
            i20 = int_gt(i16, 0)
            guard_true(i20, descr=...)
            i22 = int_add(i16, -1)
            i24 = int_eq(i16, 1)
            guard_false(i24, descr=...)
            jump(p4, p2, i22, p1, descr=...)
        """)


    def test_append(self):
        code = """
        loop(0, []).
        loop(X, [a | T]) :- X > 0, X0 is X - 1, loop(X0, T).
        length([], O, O).
        length([_|T], I, O) :- I1 is I + 1, length(T, I1, O).
        """
        code += "test(D) :- loop(3000, A), loop(1000, B), append(A, B, C), length(C, 0, D)."
        log = self.run_and_check(code, "test(D).")
        assert "D = 4000" in log.result
        loop, = log.filter_loops("loop/2")
        assert loop.match("""
            guard_not_invalidated(descr=...)
            i29 = int_gt(i18, 0)
            guard_true(i29, descr=...)
            i31 = int_add(i18, -1)
            i33 = int_eq(i18, 1)
            guard_false(i33, descr=...)
            p34 = getfield_gc_r(p26, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            guard_isnull(p34, descr=...)
            p35 = getfield_gc_r(p26, descr=<FieldP prolog.interpreter.term.Var.inst_created_after_choice_point .*>)
            i36 = instance_ptr_eq(p2, p35)
            guard_true(i36, descr=...)
            p37 = new_with_vtable(descr=...)
            p38 = new_with_vtable(descr=...)
            setfield_gc(p38, ConstPtr(ptr39), descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_0 .* pure>)
            setfield_gc(p38, p37, descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_1 .* pure>)
            setfield_gc(p26, p38, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            setfield_gc(p37, ConstPtr(null), descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            setfield_gc(p37, p2, descr=<FieldP prolog.interpreter.term.Var.inst_created_after_choice_point .*>)
            jump(p4, p2, i31, p37, p1, descr=...)
        """)
        loop, = log.filter_loops("append/3")
        assert loop.match("""
            guard_nonnull_class(p15, #, descr=...)
            guard_not_invalidated(descr=...)
            p24 = getfield_gc_r(p15, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            guard_nonnull_class(p24, #, descr=...)
            p26 = getfield_gc_r(p24, descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_0 .* pure>)
            p27 = getfield_gc_r(p24, descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_1 .* pure>)
            p28 = getfield_gc_r(p21, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            guard_isnull(p28, descr=...)
            guard_nonnull(p26, descr=...)
            p29 = getfield_gc_r(p21, descr=<FieldP prolog.interpreter.term.Var.inst_created_after_choice_point .*>)
            i30 = instance_ptr_eq(p2, p29)
            guard_true(i30, descr=...)
            p31 = new_with_vtable(descr=...)
            p32 = new_with_vtable(descr=...)
            setfield_gc(p32, p26, descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_0 .* pure>)
            setfield_gc(p32, p31, descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_1 .* pure>)
            setfield_gc(p21, p32, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            setfield_gc(p31, ConstPtr(null), descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            setfield_gc(p31, p2, descr=<FieldP prolog.interpreter.term.Var.inst_created_after_choice_point .*>)
            jump(p4, p27, p8, p31, p1, p2, descr=...)
        """)
        loop, = log.filter_loops("length/3")
        assert loop.match("""
            guard_nonnull_class(p21, #, descr=...)
            guard_not_invalidated(descr=...)
            i24 = int_add_ovf(i17, 1)
            guard_no_overflow(descr=...)
            p25 = getfield_gc_r(p21, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            guard_nonnull_class(p25, #, descr=...)
            p27 = getfield_gc_r(p25, descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_0 .* pure>)
            p28 = getfield_gc_r(p25, descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_1 .* pure>)
            jump(p4, p2, i24, p28, p9, p1, descr=...)
        """)

    def test_map(self):
        code = """
            loop(0, []).
            loop(X, [X | T]) :- X > 0, X0 is X - 1, loop(X0, T).
            add1(X, X1) :- X1 is X + 1.
            map(_, [], []).
            map(Pred, [H1 | T1], [H2 | T2]) :-
                C =.. [Pred, H1, H2],
                call(C),
                map(Pred, T1, T2).
        """
        code += "test :- loop(3000, A), map(add1, A, B), B = [3001|_], last(B, 2)."
        log = self.run_and_check(code, "test.")
        assert "yes" in log.result
        loop, = log.filter_loops("map/3")
        assert loop.match("""
            guard_nonnull_class(p31, #, descr=...)
            guard_nonnull_class(p32, #, descr=...)
            guard_not_invalidated(descr=...)
            p43 = getfield_gc_r(p31, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            guard_nonnull_class(p43, ConstClass(Number), descr=...)
            i45 = getfield_gc_i(p43, descr=<FieldS prolog.interpreter.term.Number.inst_num .* pure>)
            i47 = int_add_ovf(i45, 1)
            guard_no_overflow(descr=...)
            p48 = getfield_gc_r(p37, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            guard_isnull(p48, descr=...)
            p49 = getfield_gc_r(p37, descr=<FieldP prolog.interpreter.term.Var.inst_created_after_choice_point .*>)
            i50 = instance_ptr_eq(p2, p49)
            guard_true(i50, descr=...)
            p51 = new_with_vtable(descr=...)
            setfield_gc(p51, i47, descr=<FieldS prolog.interpreter.term.Number.inst_num .* pure>)
            setfield_gc(p37, p51, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            p52 = getfield_gc_r(p32, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            guard_nonnull_class(p52, #, descr=...)
            p55 = getfield_gc_r(p52, descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_0 .* pure>)
            p56 = getfield_gc_r(p52, descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_1 .* pure>)
            p57 = getfield_gc_r(p39, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            guard_isnull(p57, descr=...)
            p58 = getfield_gc_r(p39, descr=<FieldP prolog.interpreter.term.Var.inst_created_after_choice_point .*>)
            i59 = instance_ptr_eq(p2, p58)
            guard_true(i59, descr=...)
            p60 = new_with_vtable(descr=...)
            p61 = new_with_vtable(descr=...)
            setfield_gc(p61, p60, descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_0 .* pure>)
            p62 = new_with_vtable(descr=...)
            setfield_gc(p62, p2, descr=<FieldP prolog.interpreter.term.Var.inst_created_after_choice_point .*>)
            setfield_gc(p62, ConstPtr(null), descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            setfield_gc(p61, p62, descr=<FieldP prolog.interpreter.term.Abstract2.inst_val_1 .* pure>)
            setfield_gc(p39, p61, descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            setfield_gc(p60, ConstPtr(null), descr=<FieldP prolog.interpreter.term.BindingVar.inst_binding .*>)
            setfield_gc(p60, p2, descr=<FieldP prolog.interpreter.term.Var.inst_created_after_choice_point .*>)
            jump(p4, p7, p55, p60, p56, p62, p1, p2, descr=...)
        """)
