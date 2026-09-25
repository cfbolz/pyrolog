"""Structured syntax diagnostics shared by lexing and term parsing."""
from rpython.rlib import rutf8
from rpython.rlib.parsing.lexer import SourcePos


class SourceSpan(object):
    """Half-open byte range with zero-based lines and code-point columns."""
    def __init__(self, start, end):
        self.start = start
        self.end = end


def token_position(token, offset):
    assert offset >= 0
    start = token.source_pos
    line, column = start.lineno, start.columnno
    for code in rutf8.Utf8StringIterator(token.source[:offset]):
        if code == 10:
            line += 1
            column = 0
        else:
            column += 1
    return SourcePos(start.i + offset, line, column)


def token_span(token):
    return SourceSpan(token.source_pos, token_position(token, len(token.source)))


class SyntaxError(Exception):
    """A diagnostic with optional labels explaining the role of each span."""
    def __init__(self, msg, primary, kind='syntax_error', secondary=None,
                 expected='', found='', incomplete=False,
                 primary_label='', secondary_label=''):
        self.msg = msg
        self.primary = primary
        self.secondary = secondary
        self.primary_label = primary_label
        self.secondary_label = secondary_label
        self.kind = kind
        self.expected = expected
        self.found = found
        self.incomplete = incomplete
