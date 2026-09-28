from prolog.jittest.support import BaseTestPyrologC


class TestOperations(BaseTestPyrologC):
    def test_meta_append_continuations_have_no_body_only_slots(self):
        from rpython.tool import logparser
        from rpython.tool.jitlogparser.parser import SimpleParser
        log = self.run_and_check('''
            interpret([]).
            interpret([A|T]) :- my_clause(A, T, R), interpret(R).
            my_clause(app([], X, X), T, T).
            my_clause(app([H|T1], T2, [H|T3]), Rest,
                      [app(T1, T2, T3)|Rest]).
            my_clause(nrev([], []), T, T).
            my_clause(nrev([X|Y], Z), Rest,
                      [nrev(Y, Z1), app(Z1, [X], Z)|Rest]).
            range(0, Acc, [0|Acc]) :- !.
            range(N, Acc, L) :- M is N - 1, range(M, [N|Acc], L).
        ''', 'range(300, [], D), interpret([nrev(D, Out)]), Out = [300,299|_].')
        assert 'yes' in log.result
        # Include bridges: meta-append materializes its next rule frame on a
        # bridge back to the interpret trace's entry, not in the loop itself.
        raw = logparser.parse_log_file(str(self.tmpdir.join('jit.log')))
        frame_allocations = []
        for text in logparser.extract_category(raw, 'jit-log-opt-'):
            ops = SimpleParser.parse_from_input(text).operations
            allocations = dict((op.res, op.descr) for op in ops
                               if op.name == 'new_with_vtable')
            for op in ops:
                if op.name != 'setfield_gc' or not op.descr:
                    continue
                if 'RuleContinuationSize' not in op.descr:
                    continue
                assert op.args[1] != 'ConstPtr(null)'
                if '.inst__list_0 ' in op.descr:
                    frame_allocations.append(allocations[op.args[0]])
        assert frame_allocations
        assert set(frame_allocations) == set(['<SizeDescr 40>'])

    def test_late_locals_across_compiled_retries(self):
        log = self.run_and_check('''
            choice(a). choice(b).
            candidate(Y) :- choice(Y), X = Y, X == Y.
            loop(0) :- !.
            loop(N) :- findall(Y, candidate(Y), [a,b]),
                       M is N - 1, loop(M).
        ''', 'loop(3000).')
        assert 'yes' in log.result

    def test_recursive_locals(self):
        log = self.run_and_check('''
            build(0, []) :- !.
            build(N, [X|Xs]) :- X = f(N), M is N - 1, build(M, Xs).
        ''', 'build(3000, L), length(L, N).')
        assert 'N = 3000' in log.result

    def test_early_failure(self):
        log = self.run_and_check('''
            rejected :- fail, missing(f(X), g(X)).
            loop(0) :- !.
            loop(N) :- (rejected ; true), M is N - 1, loop(M).
        ''', 'loop(3000).')
        assert 'yes' in log.result

    def test_compiled_disjunction_with_cut_and_retry(self):
        log = self.run_and_check('''
            candidate(Y) :- (Y = a ; Y = b), X = Y, X == Y.
            committed(Y) :- (Y = a, ! ; Y = b), true.
            committed(c).
            loop(0) :- !.
            loop(N) :- findall(Y, candidate(Y), [a,b]),
                       findall(Z, committed(Z), [a]),
                       M is N - 1, loop(M).
        ''', 'loop(3000).')
        assert 'yes' in log.result

    def test_tail_branch_does_not_allocate_return_frames(self):
        log = self.run_and_check('''
            loop(0) :- !.
            loop(N) :- ((N > 0, !, M is N - 1, loop(M) ; fail) ; fail).
        ''', 'loop(3000).')
        assert 'yes' in log.result
        loop, = log.filter_loops('loop/1')
        assert not any(op.name == 'setfield_gc' and
                       'OperationContinuation' in (op.descr or '')
                       for op in loop.allops())
