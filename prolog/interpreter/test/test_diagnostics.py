# coding: utf-8
import pytest

from prolog.interpreter.syntaxerror import SyntaxError, SourceSpan
from rpython.rlib.parsing.lexer import SourcePos


def span(start, end):
    # Rendering uses byte offsets, not the lexer's code-point columns.
    return SourceSpan(SourcePos(start, 0, 0), SourcePos(end, 0, 0))


def test_two_labels():
    from prolog.interpreter.diagnostics import format_syntax_error
    source = '\n\nf(a b).'
    exc = SyntaxError("expected an operator or ',' between arguments", span(6, 7),
                      secondary=span(4, 5), primary_label='unexpected term',
                      secondary_label='preceding argument ends here')
    assert format_syntax_error(source, 'example.pl', exc) == """   ╭─[example.pl:3:5]
   │
 3 │ f(a b).
   │   │ ╰── unexpected term
   │   ╰──── preceding argument ends here
───╯
SyntaxError: expected an operator or ',' between arguments
"""


def test_unlabeled_span_is_underlined():
    from prolog.interpreter.diagnostics import format_syntax_error
    exc = SyntaxError('invalid token', span(0, 3))
    assert format_syntax_error('abc', '<query>', exc) == """   ╭─[<query>:1:1]
   │
 1 │ abc
   │ ───
───╯
SyntaxError: invalid token
"""


@pytest.mark.parametrize('source, offset, column, rendered', [
    ('\tx', 1, 8, '        x'),
    ('界\tx', 4, 8, '界      x'),
    ('éx', 2, 1, 'éx'),
    ('界x', 3, 2, '界x'),
    ('e\xcc\x81x', 3, 1, 'e\xcc\x81x'),
    ('\xffx', 1, 4, '\\xffx'),
    ('\x1bx', 1, 4, '\\x1bx'),
])
def test_display_columns(source, offset, column, rendered):
    from prolog.interpreter.diagnostics import format_syntax_error
    exc = SyntaxError('example', span(offset, offset + 1), primary_label='here')
    result = format_syntax_error(source, 'x.pl', exc)
    assert ' 1 │ ' + rendered + '\n' in result
    assert '   │ ' + ' ' * column + '╰── here\n' in result


@pytest.mark.parametrize('source', ['', 'abc', 'abc\n'])
def test_eof_has_visible_marker(source):
    from prolog.interpreter.diagnostics import format_syntax_error
    exc = SyntaxError('expected a term', span(len(source), len(source)), primary_label='here')
    result = format_syntax_error(source, 'x.pl', exc)
    assert '╰── here\n' in result
    assert ' 2 │ \n' in result if source.endswith('\n') else ' 1 │ ' in result


def test_separate_lines():
    from prolog.interpreter.diagnostics import format_syntax_error
    exc = SyntaxError('unclosed (', span(1, 2), secondary=span(7, 8),
                      primary_label='opened here', secondary_label="expected ')' here")
    assert format_syntax_error('f(a,\n b.', 'x.pl', exc) == """   ╭─[x.pl:1:2]
   │
 1 │ f(a,
   │  ╰── opened here
 2 │  b.
   │   ╰── expected ')' here
───╯
SyntaxError: unclosed (
"""


def test_distant_locations_omit_middle():
    from prolog.interpreter.diagnostics import format_syntax_error
    source = 'a\n' + 'context\n' * 20 + 'b'
    exc = SyntaxError('example', span(0, 1), secondary=span(len(source)-1, len(source)))
    result = format_syntax_error(source, 'x.pl', exc)
    assert ' ⋮\n' in result
    assert 'context' not in result
    assert ' 22 │ b\n' in result


def test_nearby_locations_show_intervening_line():
    from prolog.interpreter.diagnostics import format_syntax_error
    exc = SyntaxError('example', span(0, 1), secondary=span(10, 11))
    result = format_syntax_error('a\ncontext\nb', 'x.pl', exc)
    assert ' 2 │ context\n' in result


def test_multiline_span_labels_end_once():
    from prolog.interpreter.diagnostics import format_syntax_error
    result = format_syntax_error('ab\ncd\nef', 'x.pl',
                                 SyntaxError('example', span(1, 7), primary_label='here'))
    assert ' 1 │ ab\n   │  ─\n' in result
    assert ' 2 │ cd\n   │ ──\n' in result
    assert ' 3 │ ef\n   │ ╰── here\n' in result
    assert result.count('here') == 1


def test_half_open_multiline_span_excludes_next_line():
    from prolog.interpreter.diagnostics import format_syntax_error
    result = format_syntax_error('ab\ncd', 'x.pl',
                                 SyntaxError('example', span(0, 3), primary_label='here'))
    assert ' 2 │' not in result
    assert result.count('here') == 1


def test_color_preserves_plain_layout():
    import re
    from prolog.interpreter.diagnostics import format_syntax_error
    exc = SyntaxError('example', span(0, 2), secondary=span(1, 3),
                      primary_label='first', secondary_label='second')
    plain = format_syntax_error('abc', 'x.pl', exc)
    colored = format_syntax_error('abc', 'x.pl', exc, color=True)
    assert '\x1b[31m' in colored and '\x1b[36m' in colored
    assert re.sub(r'\x1b\[[0-9;]*m', '', colored) == plain
    assert plain.count('first') == plain.count('second') == 1


def test_renderer_is_rpython():
    from rpython.translator.translator import TranslationContext
    from prolog.interpreter.diagnostics import format_syntax_error
    from prolog.interpreter.lexer import UnicodeLexer
    from prolog.interpreter.termparser import Parser, OperatorTable
    operators = OperatorTable()

    def entry(source, color):
        try:
            Parser(UnicodeLexer().tokenize(source, eof=True), operators).parse()
        except SyntaxError as exc:
            return format_syntax_error(source, '<query>', exc, color)
        return ''

    context = TranslationContext()
    context.config.translation.list_comprehension_operations = True
    context.buildannotator().build_types(entry, [str, bool])
    context.buildrtyper().specialize()


def test_crlf_positions():
    from prolog.interpreter.diagnostics import format_syntax_error
    result = format_syntax_error('a\r\nb', 'x.pl', SyntaxError('example', span(3, 4)))
    assert '[x.pl:2:1]' in result
    assert ' 2 │ b\n' in result
    assert '\r' not in result


def test_header_uses_character_column_not_byte_or_display_column():
    from prolog.interpreter.diagnostics import format_syntax_error
    result = format_syntax_error('界x', 'x.pl', SyntaxError('example', span(3, 4)))
    assert '[x.pl:1:2]' in result
    assert '   │   ─\n' in result
