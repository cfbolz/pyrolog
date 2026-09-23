from prolog.jittest.support import BaseTestPyrologC


class TestModuleVersions(BaseTestPyrologC):
    def test_predicate_lookup_after_database_changes(self):
        source = """
            :- module(provider, [p/1]).
            p(imported).
            :- module(user, []).
            loop(0, _) :- !.
            loop(N, Expected) :-
                (catch((p(X), Status = value(X)),
                       error(existence_error(procedure, _)), Status = missing)
                 -> Status = Expected; Expected = empty),
                Next is N - 1, loop(Next, Expected).
        """
        queries = """
            once((loop(3000, missing), assertz(p(first)),
                  loop(3000, value(first)), retract(p(first)),
                  loop(3000, empty), assertz(p(second)),
                  loop(3000, value(second)), abolish(p/1),
                  loop(3000, missing), assertz(p(local)),
                  loop(3000, value(local)), use_module(provider),
                  loop(3000, value(imported)), write(check_passed), nl)).
        """
        log = self.run_and_check(source, ' '.join(queries.split()))
        assert 'check_passed\n' in log.result

    def test_module_lookup_after_creation_and_replacement(self):
        source = """
            loop(0, _) :- !.
            loop(N, Expected) :-
                catch((late:p(X), Status = value(X)),
                      error(existence_error(procedure, _)), Status = missing),
                Status = Expected,
                Next is N - 1, loop(Next, Expected).
        """
        queries = (
            'once((loop(3000, missing), assertz(late:p(first)), '
            'loop(3000, value(first)), write(created), nl)).\n'
            'module(late, []).\n'
            'assertz(p(second)).\n'
            'module(user).\n'
            'once((loop(3000, value(second)), write(check_passed), nl)).')
        log = self.run_and_check(source, queries)
        assert 'created\n' in log.result
        assert 'check_passed\n' in log.result

    def test_stable_qualified_lookup_is_eliminated(self):
        source = """
            :- module(worker, [step/2]).
            step(N, Next) :- Next is N - 1.
            :- module(user, []).
            loop(0) :- !.
            loop(N) :- worker:step(N, Next), loop(Next).
        """
        log = self.run_and_check(source, 'once(loop(3000)).')
        loops = log.filter_loops('loop/1')
        assert loops
        for loop in loops:
            names = [op.name for op in loop.allops()]
            assert 'guard_not_invalidated' in names
            assert not any(name.startswith('call') for name in names)
