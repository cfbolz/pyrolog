"""Rule operations: execution must preserve sharing across calls and retries."""
from prolog.interpreter.parsing import get_engine
from prolog.interpreter.function import Rule
from prolog.interpreter.test.tool import assert_true, assert_false, collect_all


def test_conjunction_does_not_clone_whole_body(monkeypatch):
    e = get_engine('p(X) :- X = a, X == a.')
    def forbidden(*args):
        raise AssertionError('whole rule body copied')
    monkeypatch.setattr(Rule, 'clone_body_from_rulecont', forbidden)
    assert_true('p(a).', e)


def test_body_locals_survive_backtracking():
    e = get_engine('''
        choice(a). choice(b).
        p(Y) :- choice(X), X = Y, Y == X.
        q(Y) :- choice(I), choice(X), X = Y, I == b.
    ''')
    assert [r['Y'].name() for r in collect_all(e, 'p(Y).')] == ['a', 'b']
    assert [r['Y'].name() for r in collect_all(e, 'q(Y).')] == ['a', 'b']


def test_fresh_invocations_and_nested_conjunctions():
    e = get_engine('p(X) :- (X = f(Y), Y = a), X == f(a).')
    assert_true('p(X), p(Y), X == Y.', e)
    assert_false('p(f(b)).', e)


def test_existing_control_calls_inside_conjunction():
    e = get_engine('''
        p(X) :- (X = a ; X = b), X == b.
        q(X) :- p(X), !, X == b.
        q(c).
        r(X) :- catch(throw(ball), ball, X = caught), X == caught.
    ''')
    assert [r['X'].name() for r in collect_all(e, 'q(X).')] == ['b']
    assert_true('r(caught).', e)


def test_unreached_goal_is_not_instantiated(monkeypatch):
    from prolog.interpreter.operations import CallOperation
    calls = []
    instantiate = CallOperation.instantiate
    def record(self, heap, locals):
        calls.append(self.template.signature().name)
        return instantiate(self, heap, locals)
    monkeypatch.setattr(CallOperation, 'instantiate', record)
    e = get_engine('p(X) :- fail, X = expensive(f(X), g(X)).')
    assert_false('p(_).', e)
    assert calls == ['fail']


def test_late_local_bindings_are_undone():
    # X first occurs after the choice point, but must be old enough to trail.
    e = get_engine('choice(a). choice(b). p(Y) :- choice(Y), X = Y, X == Y.')
    assert [r['Y'].name() for r in collect_all(e, 'p(Y).')] == ['a', 'b']


def test_variable_goal_and_singletons():
    e = get_engine('p(G, X) :- G, X = f(_, _).')
    assert_true('p(true, f(A, B)), A \\== B.', e)
    assert_false('p(fail, _).', e)


def test_malformed_conjunction_keeps_eager_error():
    from prolog.interpreter.test.tool import prolog_raises
    e = get_engine('p :- fail, 42. q :- true, (fail, 42).')
    prolog_raises('type_error(callable, 42)', 'p', e)
    prolog_raises('type_error(callable, 42)', 'q', e)


def test_rule_introspection_and_database_copies():
    e = get_engine('p(X) :- X = a, X == a.')
    assert_true('retract((p(X) :- B)), B = (X = a, X == a), '
                'assertz((p(X) :- B)).', e)
    assert_true('assertz(p(b)), p(a), p(b), retract(p(b)), p(a).', e)


def test_compiler_keeps_meta_calls_opaque():
    from prolog.interpreter.operations import compile_body
    from prolog.interpreter.parsing import parse_query_term
    body = parse_query_term('(a, b), call((e, f)).')
    code = compile_body(body)
    assert [op.template.signature().name for op in code] == ['a', 'b', 'call']
    assert compile_body(None) == []


def test_disjunction_does_not_instantiate_control_tree(monkeypatch):
    from prolog.interpreter.operations import CallOperation
    instantiate = CallOperation.instantiate
    def record(self, heap, locals):
        assert self.template.signature().name != ';'
        return instantiate(self, heap, locals)
    monkeypatch.setattr(CallOperation, 'instantiate', record)
    e = get_engine('p(X) :- (X = a ; X = b), X == b.')
    assert_true('p(b).', e)


def test_nested_disjunction_restores_shared_locals():
    e = get_engine('''
        p(X, Y) :- (X = a, (Y = c ; Y = d) ; X = b, Y = e),
                   Z = pair(X, Y), Z == pair(X, Y).
    ''')
    results = collect_all(e, 'p(X, Y).')
    assert [(r['X'].name(), r['Y'].name()) for r in results] == [
        ('a', 'c'), ('a', 'd'), ('b', 'e')]


def test_cut_inside_disjunction_discards_other_branch_and_clause():
    e = get_engine('''
        p(X) :- (X = a, ! ; X = b), true.
        p(c).
        q(X) :- (X = a, !, fail ; X = b), true.
        q(c).
    ''')
    assert [r['X'].name() for r in collect_all(e, 'p(X).')] == ['a']
    assert_false('q(_).', e)


def test_if_then_else_remains_opaque():
    e = get_engine('p(X) :- (true -> X = a ; X = b), X == a.')
    assert [r['X'].name() for r in collect_all(e, 'p(X).')] == ['a']
