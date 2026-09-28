"""Rule operations: execution must preserve sharing across calls and retries."""
import pytest
from prolog.interpreter.parsing import get_engine
from prolog.interpreter.function import Rule
from prolog.interpreter.test.tool import assert_true, assert_false, collect_all


@pytest.mark.parametrize('terminal_alternative', [False, True])
def test_choice_defers_alternative_success_frame(monkeypatch, terminal_alternative):
    from prolog.interpreter.continuation import (
        OperationContinuation, DoneSuccessContinuation, DoneFailureContinuation,
        FailureContinuation)
    from prolog.interpreter.heap import Heap
    from prolog.interpreter.signature import Signature
    from prolog.interpreter.term import Atom
    e = get_engine('p(X) :- (X = a ; X = b), X == X.')
    rule = e.modulewrapper.current_module.lookup(Signature.getsignature('p', 1)).rulechain
    choice = rule.operations[0]
    if terminal_alternative:
        # Exercise at(end)'s direct return as well as an ordinary alternative.
        choice.alternative_pc = len(rule.operations)
    heap = Heap()
    local = heap.newvar()
    locals = [local]
    caller = DoneSuccessContinuation(e)
    original_failure = DoneFailureContinuation(e)
    current = OperationContinuation(e, rule, caller, locals, 0)
    constructed = []
    init = OperationContinuation.__init__

    def record(self, *args):
        init(self, *args)
        constructed.append(self.pc)

    monkeypatch.setattr(OperationContinuation, '__init__', record)
    selected, failure, branch_heap = current.activate(original_failure, heap)
    assert constructed == [choice.next_pc]
    assert selected.nextcont is caller
    assert failure.nextcont is caller
    if terminal_alternative:
        assert type(failure) is FailureContinuation
    # A binding made on the first branch must be undone before resuming.
    local.unify(Atom.newatom('a'), branch_heap)
    assert local.dereference(branch_heap).name() == 'a'
    resumed, next_failure, restored_heap = failure.fail(branch_heap)
    assert restored_heap is heap
    assert local.binding is None
    assert next_failure is original_failure
    if terminal_alternative:
        assert resumed is caller
        assert constructed == [choice.next_pc]
    else:
        assert resumed.rule is rule
        assert resumed.locals is locals
        assert resumed.pc == choice.alternative_pc
        assert resumed.nextcont is caller
        assert constructed == [choice.next_pc, choice.alternative_pc]


def test_terminal_alternative_does_not_retain_locals():
    import gc
    import weakref
    from prolog.interpreter.continuation import (
        OperationContinuation, DoneSuccessContinuation, DoneFailureContinuation)
    from prolog.interpreter.heap import Heap
    from prolog.interpreter.signature import Signature
    from prolog.interpreter.term import BindingVar

    class TrackedVar(BindingVar):
        pass

    def pending_choice():
        e = get_engine('p(X) :- (X = a ; X = b).')
        rule = e.modulewrapper.current_module.lookup(Signature.getsignature('p', 1)).rulechain
        rule.operations[0].alternative_pc = len(rule.operations)
        heap = Heap()
        local = TrackedVar()
        local.created_after_choice_point = heap
        current = OperationContinuation(e, rule, DoneSuccessContinuation(e), [local], 0)
        selected, failure, branch_heap = current.activate(DoneFailureContinuation(e), heap)
        # Let the current/selected success frames go away while keeping the
        # choice pending. There are no trailed bindings retaining the local.
        return failure, weakref.ref(local)

    failure, local_ref = pending_choice()
    gc.collect()
    gc.collect()
    assert local_ref() is None
    assert not failure.is_done()


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


def test_unreached_variable_goal_does_not_raise():
    # Like SWI-Prolog, validate a variable goal only when execution reaches it,
    # even when head unification supplies a non-callable value directly.
    e = get_engine('p(G) :- fail, G.')
    assert_false('p(42).', e)


def test_variable_goal_error_follows_preceding_side_effect():
    from prolog.interpreter.test.tool import prolog_raises
    e = get_engine('seen(no). p(G) :- assertz(seen(yes)), G.')
    assert_false('seen(yes).', e)
    prolog_raises('type_error(callable, 42)', 'p(42)', e)
    assert_true('seen(yes).', e)


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


def test_generated_control_flow_matches_legacy_executor(monkeypatch):
    import random
    from prolog.interpreter.continuation import RuleContinuation
    compiled = RuleContinuation.activate

    def legacy(self, fcont, heap):
        body = self.rule.clone_body_from_rulecont(heap, self)
        if body is None:
            return self.nextcont, fcont, heap
        return self.engine.call(body, self.rule, self.nextcont, fcont, heap)

    rng = random.Random(9128)
    leaves = ['X = a', 'X = b', 'true', 'fail', '!']

    def goal(depth):
        if not depth or rng.randrange(4) == 0:
            return rng.choice(leaves)
        return '(' + goal(depth - 1) + rng.choice([', ', ' ; ']) + goal(depth - 1) + ')'

    for i in range(500):
        source = 'p(X) :- ' + goal(4) + '. p(c).'
        answers = []
        for activate in [legacy, compiled]:
            monkeypatch.setattr(RuleContinuation, 'activate', activate)
            e = get_engine(source)
            answers.append([r['X'].name() for r in
                            collect_all(e, 'p(X), nonvar(X).')])
        assert answers[0] == answers[1], (source, answers)


def test_tail_calls_do_not_retain_branch_continuations(monkeypatch):
    from prolog.interpreter.continuation import Engine
    from prolog.interpreter.term import Callable
    original_call = Engine._call
    depths = []

    def record(engine, query, rule, scont, fcont, heap):
        if isinstance(query, Callable) and query.name() == 'loop':
            depth = 0
            cont = scont
            while cont is not None:
                depth += 1
                cont = cont.nextcont
            depths.append(depth)
        return original_call(engine, query, rule, scont, fcont, heap)

    monkeypatch.setattr(Engine, '_call', record)
    recursive = 'N > 0, !, M is N - 1, loop(M)'
    for body in [recursive,
                 '(' + recursive + ' ; fail)',
                 '((' + recursive + ' ; fail) ; fail)',
                 '(fail ; (' + recursive + ' ; fail))']:
        e = get_engine('loop(0) :- !. loop(N) :- ' + body + '.')
        del depths[:]
        assert_true('loop(100).', e)
        # Cut removes alternatives; no return work remains in these tail calls.
        assert len(depths) == 101
        assert max(depths) == 2, (body, max(depths))


def test_branch_return_still_executes_following_goals():
    e = get_engine('''
        build(0, []) :- !.
        build(N, L) :- (N > 0, !, M is N - 1, build(M, T) ; fail),
                       L = [N | T].
    ''')
    assert_true('build(4, [4, 3, 2, 1]).', e)
