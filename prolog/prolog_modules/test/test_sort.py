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
