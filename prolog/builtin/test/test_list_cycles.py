import pytest

from prolog.interpreter.test.tool import assert_true, prolog_raises


@pytest.mark.parametrize('setup, goal', [
    ('L = [f|L]', 'T =.. L'),
    ('L = [a|L]', 'atom_chars(A, L)'),
    ('L = [a|L]', 'atom_chars(a, L)'),
    ('L = [97|L]', 'atom_codes(A, L)'),
    ('L = [97|L]', 'atom_codes(a, L)'),
    ("L = ['1'|L]", 'number_chars(N, L)'),
    ("L = ['1'|L]", 'number_chars(1, L)'),
    ('L = [49|L]', 'number_codes(N, L)'),
    ('L = [49|L]', 'number_codes(1, L)'),
    ('L = [quoted(true)|L]', 'write_term(a, L)'),
    ('L = [call|L]', 'leash(L)'),
    ('Tail = [b,c|Tail], L = [a|Tail]', 'atom_chars(A, L)'),
])
def test_cyclic_list_error(setup, goal):
    # Check both the error kind and the original culprit; no input is bound or
    # rewritten by detection. Error copying itself must cope with this cycle.
    assert_true('%s, catch((%s, fail), error(type_error(list, Culprit)), '
                'Culprit == L).' % (setup, goal))


@pytest.mark.parametrize('goal', ['atom_chars(a, L)', 'number_codes(1, L)'])
def test_variable_element_does_not_hide_cycle(goal):
    # Partial output elements are allowed, but an infinite spine is not.
    # The exception contains a copy, including fresh variables for its elements.
    assert_true('L = [X|L], catch((%s, fail), error(type_error(list, C)), '
                '(C = [Y|C], var(Y))), var(X).' % goal)


def test_finite_list_with_cyclic_elements():
    assert_true('X = f(X), T =.. [g,X,X], T == g(X,X), '
                'T =.. L, L == [g,X,X].')


def test_element_validation_is_preserved():
    prolog_raises('type_error(character, X)', 'X = f(X), atom_chars(A, [X])')
    prolog_raises('type_error(integer, X)', 'X = f(X), atom_codes(A, [X])')


def test_partial_lists_still_work():
    assert_true('atom_chars(ab, [a|Tail]), Tail == [b].')
    assert_true('number_codes(12, [49|Tail]), Tail == [50].')
    prolog_raises('instantiation_error', 'atom_chars(A, [a|Tail])')
    prolog_raises('type_error(list, [f|Tail])', 'T =.. [f|Tail]')
