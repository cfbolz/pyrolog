from prolog.jittest.support import BaseTestPyrologC


class TestOperations(BaseTestPyrologC):
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
