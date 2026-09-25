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


@pytest.mark.parametrize('source, closing, opening, expected, found', [
    ('f(x]', 3, 1, ')', ']'),
    ('[a,b)', 4, 0, ']', ')'),
    ('{goal]', 5, 0, '}', ']'),
    ('f([x))', 4, 2, ']', ')'),
    ('[f(x]', 4, 2, ')', ']'),
    ('f(]', 2, 1, ')', ']'),
    ('[a|)', 3, 0, ']', ')'),
])
def test_mismatched_delimiter(source, closing, opening, expected, found):
    exc = diagnostic(source)
    assert exc.kind == 'mismatched_delimiter'
    assert (exc.primary.start.i, exc.primary.end.i) == (closing, closing + 1)
    assert (exc.secondary.start.i, exc.secondary.end.i) == (opening, opening + 1)
    assert exc.expected == expected
    assert exc.found == found


@pytest.mark.parametrize('source, opening, expected', [
    ('f(', 1, ')'), ('f(x', 1, ')'), ('[', 0, ']'), ('[a|', 0, ']'),
    ('{', 0, '}'), ('{goal', 0, '}'), ('(a', 0, ')'),
    ('f([a', 2, ']'), ('f(x % comment\n  ', 1, ')'),
])
def test_unclosed_delimiter_at_eof(source, opening, expected):
    exc = diagnostic(source)
    assert exc.kind == 'unclosed_delimiter'
    assert (exc.primary.start.i, exc.primary.end.i) == (opening, opening + 1)
    assert exc.secondary.start.i == exc.secondary.end.i == len(source)
    assert exc.expected == expected
    assert exc.found == 'EOF'


def test_unclosed_delimiter_at_full_stop():
    exc = diagnostic('f(x.')
    assert exc.kind == 'unclosed_delimiter'
    assert (exc.primary.start.i, exc.primary.end.i) == (1, 2)
    assert (exc.secondary.start.i, exc.secondary.end.i) == (3, 4)
    assert exc.found == '.'


@pytest.mark.parametrize('source, closing', [('].', 0), ('a).', 1), ('(a)).', 3)])
def test_unexpected_closing_delimiter(source, closing):
    exc = diagnostic(source)
    assert exc.kind == 'unexpected_closing_delimiter'
    assert exc.primary.start.i == closing
    assert exc.secondary is None
    assert exc.expected == ''
    assert exc.found == source[closing]


def test_delimiter_locations_across_utf8_and_lines():
    exc = diagnostic('\xc3\xa9(\n  x]')
    assert position(exc.primary.start) == (7, 1, 3)
    assert position(exc.primary.end) == (8, 1, 4)
    assert position(exc.secondary.start) == (2, 0, 1)
    assert position(exc.secondary.end) == (3, 0, 2)


def test_quoted_and_commented_delimiters_are_not_syntax():
    tokens = UnicodeLexer().tokenize("f(']', /* } */ [')'], {'('}).", eof=True)
    assert Parser(tokens, default_operator_table).parse().name() == 'f'
