from prolog.jittest.support import BaseTestPyrologC


class TestAsciiGraphics(BaseTestPyrologC):
    def test_graphic_predicate_and_atoms(self):
        source = """
            ++(0) :- !.
            ++(N) :-
                '++' == ++, ':/' == :/, '++.' == ++.,
                .(a,[]) == [a],
                Next is N - 1, ++(Next).
        """
        log = self.run_and_check(source,
            '++(400), write_term(a + -1, [quoted(true)]), nl.')
        assert 'a+ -1\n' in log.result
