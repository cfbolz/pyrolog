import sys

from prolog.jittest.support import BaseTestPyrologC


class TestArithmetic(BaseTestPyrologC):
    def test_mod_minint_minus_one(self):
        # Python-level tests cannot catch the translated C division trap.
        source = """
            mod_loop(0, _, _).
            mod_loop(N, A, B) :-
                N > 0,
                R is A mod B,
                R == 0,
                Next is N - 1,
                mod_loop(Next, A, B).
        """
        log = self.run_and_check(
            source,
            'mod_loop(1000, %d, -1), write(check_passed), nl.'
            % (-sys.maxint - 1))
        assert 'check_passed\n' in log.result

    def test_bigint_int_add(self):
        source = """
            add_int(0, Acc, Acc).
            add_int(N, Acc, Result) :-
                N > 0,
                NextAcc is Acc + N,
                NextN is N - 1,
                add_int(NextN, NextAcc, Result).
        """
        log = self.run_and_check(
            source,
            'add_int(1000, 1000000000000000000000000000000, Result), '
            'Result == 1000000000000000000000000500500, '
            'write(check_passed), nl.')
        assert 'check_passed\n' in log.result
        loop, = log.filter_loops('add_int/3')
        assert loop.match("""
            ...
            p_sum = call_r(ConstClass(rbigint.int_add), p_big, i_small, descr=...)
            ...
        """)
        assert 'rbigint.fromint' not in loop.format_ops()

    def test_power_overflow(self):
        source = """
            expected(3, 16677181699666569).
            expected(4, 295147905179352825856).
            powers(0) :- !.
            powers(N) :-
                Base is 3 + N mod 2,
                Result is Base ** 34,
                expected(Base, Result),
                Next is N - 1,
                powers(Next).
        """
        log = self.run_and_check(
            source, "powers(400), write(check_passed), nl.")
        assert 'check_passed\n' in log.result
