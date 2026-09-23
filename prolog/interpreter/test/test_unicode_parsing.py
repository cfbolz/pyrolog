# coding: utf-8
import pytest
from prolog.interpreter import parsing, error
from prolog.interpreter.test.tool import assert_true


@pytest.mark.parametrize('query', [
    "é == 'é', 变量 == '变量', ǅ == 'ǅ'",
    "É = é, É == 'é', _变量 = 变量, _变量 == '变量'",
    "é == 'é', é \\== é",
    "X́ = 1, X́ == 1",
    "😀 == '😀', ≤ == '≤'",
    "atom_codes('\\u00e9\\U0001f600', [233,128512])",
    "atom_codes('\\x0\\', [0])",
    "atom_codes('it''s', [105,116,39,115])",
    "atom_codes('it\\'s', [105,116,39,115])",
    '"é😀\\n\\u20ac" == [233,128512,10,8364]',
    "0'😀 =:= 128512",
    "é == é",
])
def test_unicode_syntax(query):
    assert_true(query + '.')


@pytest.mark.parametrize('source', ["'\xff'.", '"\xc0\x80".', "'\\uD800'.", "'\\U00110000'.", "'\\u12'."])
def test_invalid_unicode_source(source):
    with pytest.raises((error.CatchableError, parsing.LexerError)):
        parsing.parse_query_term(source)


def test_lexer_byte_offsets_and_character_columns():
    tokens = parsing.lexer.tokenize('é(X).\n😀(Y).')
    y = [t for t in tokens if t.source == 'Y'][0]
    assert y.source_pos.i == len('é(X).\n😀(')
    assert y.source_pos.lineno == 1
    assert y.source_pos.columnno == 2
