from prolog.jittest.support import BaseTestPyrologC


class TestArithmetic(BaseTestPyrologC):
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
