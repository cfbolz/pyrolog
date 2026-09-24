"""Graphic tokens use maximal ASCII symbol runs, as in SWI-Prolog."""
import pytest
from prolog.interpreter import parsing
from prolog.interpreter.replpolicy import PrologInputPolicy
from prolog.interpreter.test.tool import assert_true
from prolog.interpreter.term import Callable
from prolog.builtin.formatting import TermFormatter


@pytest.mark.parametrize('atom', ['++', '+-', ':/', '#$&', '@', '...', '+.',
                                  './*', '\\==', '=..'])
def test_graphic_atoms(atom):
    tokens = parsing.lexer.tokenize(atom + ' .')
    assert [(t.name, t.source) for t in tokens] == [('ATOM', atom), ('.', '.')]
    assert parsing.parse_query_term(atom + ' .').name() == atom


@pytest.mark.parametrize('source, expected', [
    ('a.b.', [('ATOM', 'a'), ('ATOM', '.'), ('ATOM', 'b'), ('.', '.')]),
    ('.(a,b).', [('ATOM', '.'), ('(', '('), ('ATOM', 'a'), ('ATOM', ','),
                 ('ATOM', 'b'), (')', ')'), ('.', '.')]),
    ('a. b.', [('ATOM', 'a'), ('.', '.'), ('ATOM', 'b'), ('.', '.')]),
    ('a.%comment\nb.', [('ATOM', 'a'), ('.', '.'), ('ATOM', 'b'), ('.', '.')]),
    ('a./*c*/ .', [('ATOM', 'a'), ('ATOM', './*'), ('ATOM', 'c'),
                   ('ATOM', '*/'), ('.', '.')]),
    ('+/*c*/ .', [('ATOM', '+/*'), ('ATOM', 'c'), ('ATOM', '*/'), ('.', '.')]),
    ('+ /*c*/ .', [('ATOM', '+'), ('.', '.')]),
    ('!;,|', [('ATOM', '!'), ('ATOM', ';'), ('ATOM', ','), ('|', '|')]),
    ('1.5e-2.', [('FLOAT', '1.5e-2'), ('.', '.')]),
    ('X=-1.', [('VAR', 'X'), ('ATOM', '=-'), ('NUMBER', '1'), ('.', '.')]),
])
def test_graphic_boundaries(source, expected):
    assert [(t.name, t.source) for t in parsing.lexer.tokenize(source)] == expected


@pytest.mark.parametrize('source, more', [('++.', True), ('++ .', False),
                                         ('a.b', True), ('a.%comment', False)])
def test_graphic_query_completion(source, more):
    assert PrologInputPolicy().more_lines(source) == more


def test_read_graphic_atom_and_dot_functor(tmpdir):
    path = tmpdir.join('graphics.pl')
    path.write('++. . .(a,b). next.')
    assert_true("open('%s',read,S),read(S,'++.'),read(S,'.'(a,b)),"
                "read(S,next),close(S)." % path)


@pytest.mark.parametrize('name', ['++', '+.', '...', './*', '.', '/*'])
def test_graphic_quoted_output_roundtrip(name):
    rendered = TermFormatter(parsing.get_engine(''), quoted=True).format(Callable.build(name))
    assert parsing.parse_query_term(rendered + ' .').name() == name


@pytest.mark.parametrize('source', ["a + -1", "a - -1", "-(-a)", "'#' + '&'"])
def test_formatted_operators_do_not_merge(source):
    formatter = TermFormatter(parsing.get_engine(''), quoted=True)
    term = parsing.parse_query_term(source + ' .')
    rendered = formatter.format(term)
    assert_true('(%s) == (%s).' % (source, rendered))
