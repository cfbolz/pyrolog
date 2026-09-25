import pytest

from prolog.interpreter.lexer import UnicodeLexer
from prolog.interpreter.parsing import default_operator_table
from prolog.interpreter.termparser import Parser
from prolog.interpreter.syntaxerror import SyntaxError


def diagnostic(source):
    tokens = UnicodeLexer().tokenize(source, eof=True)
    with pytest.raises(SyntaxError) as exc:
        Parser(tokens, default_operator_table).parse()
    return exc.value


def position(pos):
    return pos.i, pos.lineno, pos.columnno


def test_span_labels_are_optional():
    from prolog.interpreter.syntaxerror import SourceSpan
    from rpython.rlib.parsing.lexer import SourcePos
    span = SourceSpan(SourcePos(0, 0, 0), SourcePos(1, 0, 1))
    exc = SyntaxError('example', span)
    assert exc.primary_label == ''
    assert exc.secondary_label == ''


@pytest.mark.parametrize('source, primary, secondary', [
    ('f(x', 'opened here', "expected ')' here"),
    ('f(x.', 'opened here', "expected ')' here"),
    ('f(x]', "expected ')' here", 'opened here'),
    ('a + .', 'requires a right operand', 'expected a term here'),
    ('f(,a).', 'expected an argument here', 'opened here'),
    ('[a,,b].', 'expected a list element here', 'opened here'),
    ('[a|].', 'expected a list tail here', 'opened here'),
    ('f(a b).', 'unexpected term', 'preceding argument ends here'),
    ('[a b].', 'unexpected term', 'preceding list element ends here'),
    ('a b.', 'unexpected term', 'preceding term ends here'),
    ('f (a).', 'whitespace before this parenthesis', 'functor name here'),
    ('[a|b,c].', "expected ']' here", 'list tail starts after this'),
    ('a. b.', 'unexpected input', 'term ended here'),
])
def test_span_labels_explain_related_locations(source, primary, secondary):
    exc = diagnostic(source)
    assert exc.primary_label == primary
    assert exc.secondary_label == secondary


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
    assert exc.incomplete
    assert not hasattr(exc, 'parser')
    assert not hasattr(exc, 'tok')


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
    assert not exc.incomplete


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
    assert exc.incomplete


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
    assert exc.primary_label == 'opened here'
    assert exc.secondary_label == "expected ')' here"


def test_query_preserves_diagnostic():
    from prolog.interpreter import parsing, error
    with pytest.raises(error.CatchableError) as caught:
        parsing.parse_query_term('f(x].')
    exc = caught.value.parse_error
    assert exc.kind == 'mismatched_delimiter'
    assert exc.primary.start.i == 3
    assert exc.secondary.start.i == 1
    assert caught.value.term.argument_at(0).name() == 'syntax_error'
    assert exc.primary_label == "expected ')' here"
    assert exc.secondary_label == 'opened here'


def test_query_eof_preserves_trailing_layout_position():
    from prolog.interpreter import parsing, error
    with pytest.raises(error.CatchableError) as caught:
        parsing.parse_query_term('f(x\n  ')
    exc = caught.value.parse_error
    assert position(exc.secondary.start) == (6, 1, 2)


def test_file_lexer_error_preserves_syntax_diagnostic():
    from prolog.interpreter import parsing, error
    with pytest.raises(error.PrologParseError) as caught:
        parsing.parse_file('` .')
    assert caught.value.parse_error.kind == 'invalid_token'


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
    assert exc.primary_label == '%s operand requires precedence %s' % (side, exc.expected)
    assert exc.secondary_label == 'operand has precedence %s' % exc.found


def test_postfix_precedence_clash():
    from prolog.interpreter.termparser import OperatorTable
    table = OperatorTable()
    table.add('@', 400, 'xf')
    with pytest.raises(SyntaxError) as caught:
        Parser(UnicodeLexer().tokenize('a @ @ .'), table).parse()
    exc = caught.value
    assert exc.kind == 'precedence_clash'
    assert exc.primary.start.i == 4
    assert exc.secondary.start.i == 2
    assert exc.expected == 'at most 399'
    assert exc.found == '400'


def test_left_precedence_clash_takes_priority_when_both_operands_clash():
    exc = diagnostic('a=b= \\+ c.')
    assert exc.kind == 'precedence_clash'
    assert exc.primary.start.i == 3
    assert exc.secondary.start.i == 1
    assert 'left operand' in exc.msg


def test_expression_precedence_limit_reports_actual_and_limit():
    parser = Parser(UnicodeLexer().tokenize('1+2.'), default_operator_table)
    with pytest.raises(SyntaxError) as caught:
        parser._parse_op_expr(400, '.')
    exc = caught.value
    assert exc.kind == 'precedence_limit'
    assert exc.primary.start.i == 1
    assert exc.expected == 'at most 400'
    assert exc.found == '500'


@pytest.mark.parametrize('source, start, end, kind', [
    ("'abc\\qxyz'.", 4, 6, 'invalid_escape'),
    ('"abc\\qxyz".', 4, 6, 'invalid_escape'),
    ("'\\uD800'.", 1, 7, 'invalid_character_code'),
    ("'\\u12Z4'.", 1, 6, 'invalid_escape'),
    ("'\\u12'.", 1, 5, 'invalid_escape'),
    ("0'\\uD800.", 2, 8, 'invalid_character_code'),
    ("'\\x110000\\'.", 1, 10, 'invalid_character_code'),
    ("'\\\xc3\xa9'.", 1, 4, 'invalid_escape'),
])
def test_invalid_escape_points_to_escape_sequence(source, start, end, kind):
    exc = diagnostic(source)
    assert exc.kind == kind
    assert (exc.primary.start.i, exc.primary.end.i) == (start, end)
    assert exc.secondary is None


def test_escape_position_after_utf8_and_newline():
    exc = diagnostic("'\xc3\xa9\nxy\\q'.")
    assert position(exc.primary.start) == (6, 1, 2)
    assert position(exc.primary.end) == (8, 1, 4)


def test_float_overflow_has_stable_kind():
    exc = diagnostic('1.0e999.')
    assert exc.kind == 'float_overflow'
    assert (exc.primary.start.i, exc.primary.end.i) == (0, 7)


@pytest.mark.parametrize('name, source, kind', [
    ('NUMBER', '0xG', 'invalid_integer'),
    ('NUMBER', "0'ab", 'invalid_character_literal'),
    ('FLOAT', '1.2.3', 'invalid_float'),
])
def test_defensive_literal_errors(name, source, kind):
    # These malformed tokens normally fail lexing; the parser still validates
    # tokens supplied directly by its callers.
    from rpython.rlib.parsing.lexer import Token, SourcePos
    tokens = [Token(name, source, SourcePos(0, 0, 0)),
              Token('.', '.', SourcePos(len(source), 0, len(source)))]
    with pytest.raises(SyntaxError) as caught:
        Parser(tokens, default_operator_table).parse()
    assert caught.value.kind == kind
    assert caught.value.primary.start.i == 0
    assert caught.value.primary.end.i == len(source)


def test_expected_separator_reports_spelling_not_token_class():
    parser = Parser(UnicodeLexer().tokenize('foo.'), default_operator_table)
    with pytest.raises(SyntaxError) as caught:
        parser._expect('ATOM', ',')
    exc = caught.value
    assert exc.kind == 'unexpected_token'
    assert exc.expected == ','
    assert exc.found == 'foo'
    assert "found 'foo'" in exc.msg


def test_file_location_uses_precise_escape_span():
    from prolog.interpreter import parsing, error
    with pytest.raises(error.PrologParseError) as caught:
        parsing.parse_file("'first\nxy\\q'.", file_name='example.pl')
    assert caught.value.line_number == 1
    assert position(caught.value.parse_error.primary.start) == (9, 1, 2)


@pytest.mark.parametrize('source, primary, secondary, expected', [
    ('f(a b).', 4, 2, "operator or ','"),
    ('f(g(a) h(b)).', 7, 5, "operator or ','"),
    ('f(a+1 b).', 6, 4, "operator or ','"),
    ('f(a /* gap */ b).', 14, 2, "operator or ','"),
    ('[a b].', 3, 1, "operator, ',' or '|'"),
    ('[f(a) g(b)].', 6, 4, "operator, ',' or '|'"),
    ('f([a b]).', 5, 3, "operator, ',' or '|'"),
    ('[f(a b)].', 5, 3, "operator or ','"),
])
def test_missing_separator_context(source, primary, secondary, expected):
    exc = diagnostic(source)
    assert exc.kind == 'missing_separator'
    assert exc.primary.start.i == primary
    assert exc.secondary.start.i == secondary
    assert exc.expected == expected
    assert expected in exc.msg


@pytest.mark.parametrize('source', ['(a b).', '{a b}.', '[a|b c].', 'f((a b)).'])
def test_no_separator_hint_in_nested_single_expression_context(source):
    exc = diagnostic(source)
    assert exc.kind == 'missing_operator'
    assert exc.expected == 'operator'


@pytest.mark.parametrize('source', [
    'a b.',
    'f :-\n    g,\n    h\n\ng :- throw(error).',
    'f(a) g(b).',
    '(a) b.',
    '[a] b.',
    '{a} b.',
])
def test_full_stop_hint_between_outermost_terms(source):
    exc = diagnostic(source)
    assert exc.kind == 'missing_operator'
    assert exc.expected == "operator or '.'"
    assert exc.msg == "expected an operator or '.' between terms"
    assert exc.primary_label == 'unexpected term'
    assert exc.secondary_label == 'preceding term ends here'


def test_separator_error_keeps_utf8_and_multiline_positions():
    exc = diagnostic('f(\xc3\xa9\n  \xce\xb2).')
    assert exc.kind == 'missing_separator'
    assert position(exc.primary.start) == (7, 1, 2)
    assert position(exc.primary.end) == (9, 1, 3)
    assert position(exc.secondary.start) == (2, 0, 2)
    assert position(exc.secondary.end) == (4, 0, 3)


def test_file_uses_diagnostic_renderer():
    from prolog.interpreter import parsing, error
    from prolog.interpreter.diagnostics import format_syntax_error
    source = 'f(a b).'
    with pytest.raises(error.PrologParseError) as caught:
        parsing.parse_file(source, file_name='example.pl')
    exc = caught.value
    assert exc.message + '\n' == format_syntax_error(source, 'example.pl', exc.parse_error)


@pytest.mark.parametrize('color', [False, True])
def test_file_diagnostic_is_rendered_only_when_requested(monkeypatch, color):
    from prolog.interpreter import parsing, diagnostics, error
    original = diagnostics.format_syntax_error
    renders = []

    def render(source, filename, exc, color=False):
        renders.append(color)
        return original(source, filename, exc, color)

    monkeypatch.setattr(diagnostics, 'format_syntax_error', render)
    monkeypatch.setattr(error, 'can_colorize', lambda fd: color)
    with pytest.raises(error.PrologParseError) as caught:
        parsing.parse_file('f(a b).', file_name='<query>')
    assert renders == []
    text = caught.value.format_message()
    assert renders == [color]
    assert ('\x1b[31m' in text) == color
    assert 'SyntaxError:' in text
    plain = caught.value.message
    assert '\x1b' not in plain
    assert renders == ([True, False] if color else [False])
    assert caught.value.message == plain
    assert renders == ([True, False] if color else [False])
