import pytest

from prolog.interpreter.test.tool import (
    assert_false, assert_true, collect_all, get_engine, prolog_raises)


def test_retractall_matches_heads_of_facts_and_rules():
    engine = get_engine('''
        p(a, a).
        p(a, a).
        p(b, b) :- throw(body_must_not_run).
        p(a, b).
        p(c, d) :- true.
        p(keep).
    ''', load_system=True)
    assert_true('retractall(p(X, X)), var(X), p(keep).', engine)
    answers = collect_all(engine, 'p(X, Y).')
    assert [(a['X'].name(), a['Y'].name()) for a in answers] == [
        ('a', 'b'), ('c', 'd')]


def test_retractall_succeeds_once_and_leaves_template_unbound():
    engine = get_engine('p(a). p(b) :- true.', load_system=True)
    assert len(collect_all(engine, 'retractall(p(X)), var(X).')) == 1
    assert_false('p(_).', engine)
    assert_true('assertz(p(new)), p(new).', engine)


@pytest.mark.parametrize('goal', [
    'retractall(missing(X)), var(X)',
    'retractall(p(absent)), p(keep)',
    'retractall(p(_)), retractall(p(_))',
])
def test_retractall_succeeds_without_matches(goal):
    engine = get_engine('p(keep).', load_system=True)
    assert len(collect_all(engine, goal + '.')) == 1


def test_retractall_removals_survive_backtracking():
    engine = get_engine('p(a). p(b).', load_system=True)
    assert_true('(retractall(p(X)), fail; var(X)).', engine)
    assert_false('p(_).', engine)


@pytest.mark.parametrize('goal', [
    'left:clear',
    'left:retractall(p(_))',
    'retractall(left:p(_))',
    'M = left, H = p(_), retractall(M:H)',
    'Target = left:p(_), retractall(Target)',
])
def test_retractall_uses_callers_or_explicit_module(goal):
    engine = get_engine('''
        p(user).
        :- module(left, []).
        p(fact).
        p(rule) :- true.
        clear :- retractall(p(_)).
        :- module(right, []).
        p(keep).
    ''', load_system=True)
    assert_true(goal + ', right:p(keep), user:p(user).', engine)
    assert_false('left:p(_).', engine)


@pytest.mark.parametrize('goal, exception', [
    ('retractall(X)', 'instantiation_error'),
    ('retractall(42)', 'type_error(callable, 42)'),
    ('retractall(user:X)', 'instantiation_error'),
    ('retractall(user:42)', 'type_error(callable, 42)'),
    ('retractall(atom(_))', 'permission_error(modify, static_procedure, atom/1)'),
])
def test_retractall_propagates_errors(goal, exception):
    engine = get_engine('', load_system=True)
    prolog_raises(exception, goal, engine)
