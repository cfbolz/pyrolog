"""Integration tests for the rational-tree DFA example (see the .pl file)."""
import itertools
import os

import pytest

from prolog.interpreter.parsing import get_engine
from prolog.interpreter.test.tool import assert_true, assert_false


with open(os.path.join(os.path.dirname(__file__), 'dfa_rational_trees.pl')) as f:
    DFA_SOURCE = f.read()

BLOG_DOT = '''digraph G {
start [label="", shape=none]
start -> 0
0 [shape=circle]
0 -> 1 [label=a]
0 -> 1 [label=b]
1 [shape=circle]
1 -> 2 [label=a]
1 -> 1 [label=b]
2 [shape=doublecircle]
2 -> 2 [label=a]
2 -> 2 [label=b]
}
'''


@pytest.fixture
def engine():
    return get_engine(DFA_SOURCE, load_system=True)


def test_equivalent_cycles_with_different_periods(engine):
    assert_true('dfa_a_plus(A), dfa_a_plus_inefficient(B), '
                'A == B, A = B, ground(A), term_variables(A, []), '
                'not(acyclic_term(A)).', engine)
    assert_false('dfa_a_plus(A), dfa_blog_post(B), A = B.', engine)


@pytest.mark.parametrize('constructor, size', [
    ('dfa_a_plus', 2), ('dfa_a_plus_inefficient', 2), ('dfa_blog_post', 3),
])
def test_number_states(engine, constructor, size):
    assert_true('%s(D), number_states(D, L), length(L, %d), '
                'ground(L), term_variables(L, []).' % (constructor, size), engine)


def test_matching_before_and_after_minimization(engine):
    # Exhaustively check short words against independent language descriptions.
    # Running both matches on the same graph also checks that failed unifications
    # in member/2 and not/1 do not corrupt the automaton on backtracking.
    for constructor in ['dfa_a_plus', 'dfa_a_plus_inefficient', 'dfa_blog_post']:
        for length in range(6):
            for word in itertools.product('ab', repeat=length):
                accepted = (bool(word) and 'b' not in word)
                if constructor == 'dfa_blog_post':
                    accepted = 'a' in word[1:]
                match = 'match([%s], D)' % ','.join(word)
                if not accepted:
                    match = 'not(%s)' % match
                assert_true('%s(D), %s, number_states(D, _), %s.' %
                            (constructor, match, match), engine)


def test_copy_and_dot(engine, capfd):
    assert_true('dfa_blog_post(D), copy_term(D, Copy), D == Copy, '
                'to_dot(Copy).', engine)
    out, err = capfd.readouterr()
    assert out == BLOG_DOT
    assert not err


def test_print_numbered_states(engine, capfd):
    assert_true('dfa_blog_post(D), number_states(D, L), '
                'write_term(L, [quoted(true)]).', engine)
    out, err = capfd.readouterr()
    assert out.startswith("@(")
    assert '...' not in out
    assert not err
    # Reconstruct the printed graph and check semantic identity, without relying
    # on generated label names or a particular factorization of the cycles.
    engine.runstring('''
        bind_equations([]).
        bind_equations([X=Y|Rest]) :- X=Y, bind_equations(Rest).
    ''')
    assert_true('dfa_blog_post(D), number_states(D, L), '
                "%s = '@'(Template, Bindings), bind_equations(Bindings), "
                'Template == L.' % out.encode('ascii'), engine)
