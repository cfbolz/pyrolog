import pytest

from prolog.interpreter.lexer import UnicodeLexer
from prolog.interpreter.parsing import default_operator_table
from prolog.interpreter.termparser import Parser, ParseError


def diagnostic(source):
    tokens = UnicodeLexer().tokenize(source, eof=True)
    with pytest.raises(ParseError) as exc:
        Parser(tokens, default_operator_table).parse()
    return exc.value


def position(pos):
    return pos.i, pos.lineno, pos.columnno


def test_error_token_has_full_utf8_span():
    exc = diagnostic('a \xc3\xa9clair.')
    assert exc.kind == 'syntax_error'
    assert position(exc.primary.start) == (2, 0, 2)
    assert position(exc.primary.end) == (9, 0, 8)
    assert exc.secondary is None


def test_multiline_error_token_span():
    exc = diagnostic("a 'b\nc'.")
    assert position(exc.primary.start) == (2, 0, 2)
    assert position(exc.primary.end) == (7, 1, 2)


def test_eof_span_includes_trailing_layout_and_comments():
    source = 'a  % comment\n\t'
    exc = diagnostic(source)
    assert position(exc.primary.start) == (len(source), 1, 1)
    assert position(exc.primary.end) == position(exc.primary.start)
    assert exc.secondary is None


def test_empty_input_position():
    exc = diagnostic('')
    assert position(exc.primary.start) == (0, 0, 0)
    assert position(exc.primary.end) == (0, 0, 0)
