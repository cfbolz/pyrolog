import random

import pytest

from prolog.interpreter.continuation import Engine
from prolog.interpreter.test.tool import assert_false, assert_true, collect_all, prolog_raises


@pytest.mark.parametrize('values', [
    [], [1], [1, 1], [2, 1], [1, 2], [3, 1, 2],
    [3, 1, 3, 2, 1, 2, 3], [4] * 17,
    range(32), range(32, -1, -1),
    [5, 4, 3, 2, 1, 0, 1, 2, 3, 4, 5],
])
def test_sort_integers(values):
    engine = Engine(load_system=True)
    assert_true('sort(%s, Sorted), Sorted == %s.' %
                (values, sorted(set(values))), engine)


def test_sort_random_lists():
    engine = Engine(load_system=True)
    randomizer = random.Random(42)
    for length in [7, 16, 31, 64, 127, 256]:
        values = [randomizer.randrange(-30, 31) for _ in range(length)]
        assert_true('sort(%s, Sorted), Sorted == %s.' %
                    (values, sorted(set(values))), engine)


def test_sort_mixed_terms():
    engine = Engine(load_system=True)
    assert_true('sort([f(b), a, 2, f(a), 1.0, 1, a, f(a), -2, g(a,b)], S), '
                'S == [-2, 1.0, 1, 2, a, f(a), f(b), g(a,b)].', engine)


def test_sort_preserves_variable_identity_without_unifying_elements():
    engine = Engine(load_system=True)
    assert_true('sort([X, Y, X, Y], S), var(X), var(Y), X \\== Y, '
                '(S == [X,Y]; S == [Y,X]).', engine)
    assert_true('sort([f(X), f(X)], S), S == [f(X)], var(X).', engine)


def test_sort_unifies_output_only_after_sorting():
    engine = Engine(load_system=True)
    assert_true('sort([X, 1], [2, 1]), X == 2.', engine)
    assert_true('sort([X, Y], [a, a]), X == a, Y == a.', engine)
    assert_true('sort([b, a, b], [a|Tail]), Tail == [b].', engine)
    assert_false('sort([b, a], [b, a]).', engine)
    assert_false('sort([a, a], [a, a]).', engine)


@pytest.mark.parametrize('goal', [
    'sort([], S), S == []',
    'sort([a], S), S == [a]',
    'sort([c, a, b, a], S), S == [a, b, c]',
])
def test_sort_has_one_solution(goal):
    engine = Engine(load_system=True)
    assert len(collect_all(engine, goal + '.')) == 1


@pytest.mark.parametrize('goal, exception', [
    ('sort(X, S)', 'instantiation_error'),
    ('sort(X, [a,b])', 'instantiation_error'),
    ('sort([a|Tail], S)', 'instantiation_error'),
    ('sort([a|Tail], [a,b])', 'instantiation_error'),
    ('sort(a, S)', 'type_error(list, a)'),
    ('sort([a|bad], S)', 'type_error(list, [a|bad])'),
])
def test_sort_invalid_input(goal, exception):
    prolog_raises(exception, goal, Engine(load_system=True))


@pytest.mark.parametrize('setup', [
    'L = [a|L]',
    'Tail = [b,c|Tail], L = [a|Tail]',
])
def test_sort_rejects_cyclic_spine(setup):
    engine = Engine(load_system=True)
    assert_true('%s, '
                'catch((sort(L, _), fail), error(type_error(list, C)), C == L).'
                % setup,
                engine)


def test_sort_length_only_checks_the_spine():
    engine = Engine(load_system=True)
    assert_true('X = f(X), sort([X], S), S == [X].', engine)
    prolog_raises('instantiation_error',
                  'X = f(X), sort([X|Tail], _)', engine)


def test_sort_does_not_modify_input_list():
    engine = Engine(load_system=True)
    assert_true('L = [c,a,b,a], sort(L, [a,b,c]), L == [c,a,b,a].', engine)


@pytest.mark.parametrize('order, expected', [
    ('@<', '[1-b,2-a,3-d]'), ('<', '[1-b,2-a,3-d]'),
    ('@=<', '[1-b,1-e,2-a,2-c,2-f,3-d]'),
    ('=<', '[1-b,1-e,2-a,2-c,2-f,3-d]'),
    ('@>', '[3-d,2-a,1-b]'), ('>', '[3-d,2-a,1-b]'),
    ('@>=', '[3-d,2-a,2-c,2-f,1-b,1-e]'),
    ('>=', '[3-d,2-a,2-c,2-f,1-b,1-e]'),
])
def test_sort_four_orders_are_stable(order, expected):
    engine = Engine(load_system=True)
    goal = "sort(1, '%s', [2-a,1-b,2-c,3-d,1-e,2-f], S), S == %s." % (
        order, expected)
    assert len(collect_all(engine, goal)) == 1


def test_sort_four_key_selection():
    engine = Engine(load_system=True)
    assert_true('sort(0, @>=, [b,a,b,c], S), S == [c,b,b,a].', engine)
    assert_true('sort(2, @=<, [f(a,2),g(b,1),f(c,2)], S), '
                'S == [g(b,1),f(a,2),f(c,2)].', engine)
    assert_true('sort([2,1], @<, [f(a,g(2)),f(b,g(1)),f(c,g(2))], S), '
                'S == [f(b,g(1)),f(a,g(2))].', engine)
    assert_true('sort(1, @=<, [X-a,X-b], S), '
                'S == [X-a,X-b], var(X).', engine)
    assert_true('sort(1, @=<, [X-a,1-b], [2-a,1-b]), X == 2.', engine)


@pytest.mark.parametrize('goal, exception', [
    ('sort(_, @<, [], _)', 'instantiation_error'),
    ('sort(-1, @<, [], _)', 'domain_error(not_less_than_one,-1)'),
    ('sort(1.5, @<, [], _)', 'type_error(sort_key,1.5)'),
    ('sort([1,0], @<, [], _)', 'domain_error(not_less_than_one,0)'),
    ('sort([_], @<, [], _)', 'instantiation_error'),
    ('sort([1|X], @<, [], _)', 'type_error(sort_key,[1|X])'),
    ('sort(0, _, [], _)', 'instantiation_error'),
    ('sort(0, bad, [], _)', 'domain_error(order,bad)'),
    ('sort(0, 42, [], _)', 'type_error(atom,42)'),
    ('sort(1, @<, [a], _)', 'type_error(compound,a)'),
    ('sort(1, @<, [_], _)', 'instantiation_error'),
    ('sort(2, @<, [f(a)], _)', 'existence_error(argument,2,f(a))'),
    ('sort([1,2], @<, [f(g(a))], _)', 'existence_error(argument,2,g(a))'),
    ('keysort([a], _)', 'type_error(pair,a)'),
    ('keysort([f(a,b)], _)', 'type_error(pair,f(a,b))'),
    ('keysort([_], _)', 'instantiation_error'),
    ('keysort([a-b|_], _)', 'instantiation_error'),
    ('keysort([a-b|bad], _)', 'type_error(list,[a-b|bad])'),
])
def test_sort_four_and_keysort_errors(goal, exception):
    prolog_raises(exception, goal, Engine(load_system=True))


def test_keysort_preserves_pairs_and_variable_values():
    engine = Engine(load_system=True)
    assert_true('keysort([b-X,a-Y,b-Z,a-Y], S), '
                'S == [a-Y,a-Y,b-X,b-Z], var(X), var(Y), var(Z).', engine)
    for goal in ['keysort([], S), S == []',
                 'keysort([a-b], S), S == [a-b]',
                 'keysort([b-x,a-y,b-z], S), S == [a-y,b-x,b-z]']:
        assert len(collect_all(engine, goal + '.')) == 1
    assert_false('keysort([a-b,a-b], [a-b]).', engine)
