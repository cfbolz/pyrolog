import pytest

from prolog.interpreter.test.test_rational_tree_dfa import DFA_SOURCE, BLOG_DOT
from prolog.jittest.support import run_log


@pytest.mark.parametrize('jit_options', ['off', 'threshold=40'])
def test_compiled_dfa_minimization(tmpdir, jit_options):
    log = run_log(tmpdir, DFA_SOURCE,
        'once((dfa_a_plus(A), dfa_a_plus_inefficient(B), A == B, A = B, '
        'number_states(B, L), length(L, 2), '
        'dfa_blog_post(D), copy_term(D, C), C == D, '
        'ground(C), term_variables(C, []), not(acyclic_term(C)), '
        'number_states(C, States), length(States, 3), '
        'match([b,a,b], C), not(match([a,b,b], C)), '
        'to_dot(C), write(dfa_checks_passed), nl)).', jit_options)
    assert BLOG_DOT in log.result
    assert 'dfa_checks_passed\n' in log.result
    assert 'yes' in log.result
    assert 'Nein' not in log.result
