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
