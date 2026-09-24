# coding: utf-8
"""Unicode solo characters follow SWI's newer Unicode source syntax.

https://www.swi-prolog.org/pldoc/man?section=unicodesyntax
SWI 9.2 instead joined adjacent Unicode symbols into graphic atoms.
"""
import pytest
from prolog.interpreter import parsing
from prolog.interpreter.term import Callable
from prolog.builtin.formatting import TermFormatter


@pytest.mark.parametrize('symbol', ['≤', '€', '˄', '😀', '＿', '—', '·'])
def test_unicode_solo_categories(symbol):
    tokens = parsing.lexer.tokenize(symbol + symbol + '.')
    assert [(t.name, t.source) for t in tokens] == [
        ('ATOM', symbol), ('ATOM', symbol), ('.', '.')]
    assert tokens[1].source_pos.i == len(symbol)
    assert tokens[1].source_pos.columnno == 1
    assert parsing.parse_query_term(symbol + '.').name() == symbol


@pytest.mark.parametrize('source, expected', [
    ('+≤', ['+', '≤']), ('≤+', ['≤', '+']),
    ('≤≥', ['≤', '≥']), ('≤=..≥', ['≤', '=..', '≥']),
    ('—≤·', ['—', '≤', '·']),
    ('≤/* comment */≥', ['≤', '≥']),
    ('≤% comment\n≥', ['≤', '≥']),
    ('a·b', ['a·b']), ('ˆname', ['ˆname']),
    ('℘name', ['℘name']), ('℮name', ['℮name']),
])
def test_unicode_solo_boundaries(source, expected):
    assert [t.source for t in parsing.lexer.tokenize(source)] == expected


@pytest.mark.parametrize('name', ['≤≥', '+≤', '≤+', '——', '··'])
def test_multiple_symbols_are_quoted(name):
    formatter = TermFormatter(parsing.get_engine(''), quoted=True)
    rendered = formatter.format(Callable.build(name))
    assert rendered == "'" + name + "'"
    assert parsing.parse_query_term(rendered + '.').name() == name


def test_ascii_prefix_operator_next_to_unicode_solo():
    parsed = parsing.parse_query_term('+≤.')
    assert parsed.name() == '+'
    assert parsed.argument_at(0).name() == '≤'
