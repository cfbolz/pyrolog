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
    assert exc.kind == 'missing_operator'
    assert position(exc.primary.start) == (2, 0, 2)
    assert position(exc.primary.end) == (9, 0, 8)
    assert exc.secondary.start.i == 0


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


def test_file_preserves_diagnostic_for_unterminated_last_term():
    from prolog.interpreter import parsing, error
    source = 'good.\nf(x % trailing comment\n  '
    with pytest.raises(error.PrologParseError) as caught:
        parsing.parse_file(source, file_name='example.pl')
    exc = caught.value.parse_error
    assert exc.kind == 'unclosed_delimiter'
    assert position(exc.primary.start) == (7, 1, 1)
    assert position(exc.secondary.start) == (len(source), 2, 2)
    assert caught.value.file_name == 'example.pl'
    assert caught.value.line_number == 1


def test_query_preserves_diagnostic():
    from prolog.interpreter import parsing, error
    with pytest.raises(error.CatchableError) as caught:
        parsing.parse_query_term('f(x].')
    exc = caught.value.parse_error
    assert exc.kind == 'mismatched_delimiter'
    assert exc.primary.start.i == 3
    assert exc.secondary.start.i == 1
    assert caught.value.term.argument_at(0).name() == 'syntax_error'


def test_query_eof_preserves_trailing_layout_position():
    from prolog.interpreter import parsing, error
    with pytest.raises(error.CatchableError) as caught:
        parsing.parse_query_term('f(x\n  ')
    exc = caught.value.parse_error
    assert position(exc.secondary.start) == (6, 1, 2)


def test_file_lexer_error_has_no_parser_diagnostic():
    from prolog.interpreter import parsing, error
    with pytest.raises(error.PrologParseError) as caught:
        parsing.parse_file('` .')
    assert caught.value.parse_error is None


@pytest.mark.parametrize('source, primary, secondary', [
    ('a + .', 2, 4), ('a +', 2, 3), ('f(a+,b).', 3, 4),
])
def test_missing_operand_points_to_operator(source, primary, secondary):
    exc = diagnostic(source)
    assert exc.kind == 'missing_operand'
    assert exc.primary.start.i == primary
    assert exc.secondary.start.i == secondary
    assert 'right operand' in exc.msg
    assert '+' in exc.msg


@pytest.mark.parametrize('source, kind, primary, secondary', [
    ('f().', 'missing_argument', 2, 1),
    ('f(a,,b).', 'missing_argument', 4, 1),
    ('f(a,).', 'missing_argument', 4, 1),
    ('[,a].', 'missing_list_element', 1, 0),
    ('[a,].', 'missing_list_element', 3, 0),
    ('[a|].', 'missing_list_tail', 3, 0),
    ('().', 'missing_term', 1, 0),
])
def test_missing_term_context(source, kind, primary, secondary):
    exc = diagnostic(source)
    assert exc.kind == kind
    assert exc.primary.start.i == primary
    assert exc.secondary.start.i == secondary


@pytest.mark.parametrize('source', ['f (x).', 'f/*comment*/(x).'])
def test_functor_separation(source):
    exc = diagnostic(source)
    assert exc.kind == 'functor_whitespace'
    assert exc.primary.start.i == source.index('(')
    assert exc.secondary.start.i == 0
    assert 'immediately' in exc.msg


def test_trailing_input_points_back_to_full_stop():
    exc = diagnostic('a. b.')
    assert exc.kind == 'trailing_input'
    assert exc.primary.start.i == 3
    assert exc.secondary.start.i == 1


def test_missing_full_stop_at_eof():
    exc = diagnostic('f(x)  ')
    assert exc.kind == 'missing_full_stop'
    assert exc.primary.start.i == 6
    assert exc.expected == '.'
    assert exc.found == 'EOF'


@pytest.mark.parametrize('source', ['[a|b,c].', '[a|b|c].'])
def test_extra_separator_after_list_tail(source):
    exc = diagnostic(source)
    assert exc.kind == 'invalid_list_tail'
    assert exc.primary.start.i == 4
    assert exc.secondary.start.i == 2


@pytest.mark.parametrize('source, primary, secondary, side', [
    ('1=2=3.', 3, 1, 'left'),
    ('- - X.', 0, 2, 'right'),
])
def test_precedence_clash_identifies_both_operators(source, primary, secondary, side):
    exc = diagnostic(source)
    assert exc.kind == 'precedence_clash'
    assert exc.primary.start.i == primary
    assert exc.secondary.start.i == secondary
    assert side + ' operand' in exc.msg
    assert 'precedence' in exc.msg


def test_postfix_precedence_clash():
    from prolog.interpreter.termparser import OperatorTable
    table = OperatorTable()
    table.add('@', 400, 'xf')
    with pytest.raises(ParseError) as caught:
        Parser(UnicodeLexer().tokenize('a @ @ .'), table).parse()
    exc = caught.value
    assert exc.kind == 'precedence_clash'
    assert exc.primary.start.i == 4
    assert exc.secondary.start.i == 2
    assert exc.expected == 'at most 399'
    assert exc.found == '400'


def test_expression_precedence_limit_reports_actual_and_limit():
    parser = Parser(UnicodeLexer().tokenize('1+2.'), default_operator_table)
    with pytest.raises(ParseError) as caught:
        parser._parse_op_expr(400, '.')
    exc = caught.value
    assert exc.kind == 'precedence_limit'
    assert exc.primary.start.i == 1
    assert exc.expected == 'at most 400'
    assert exc.found == '500'
