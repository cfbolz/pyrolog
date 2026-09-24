"""Shared Unicode classification; all text is stored as UTF-8 bytes."""
from rpython.rlib import rutf8
from rpython.rlib.unicodedata import unicodedb_15_0_0 as unicodedb


def identifier_start(code):
    return code == 95 or unicodedb.isxidstart(code)


def identifier_continue(code):
    return code == 95 or unicodedb.isxidcontinue(code)


def variable_start(code):
    return code == 95 or unicodedb.category(code) == 'Lu'


def plain_atom(text):
    if not text:
        return False
    first = rutf8.codepoint_at_pos(text, 0)
    if not identifier_start(first) or variable_start(first):
        return False
    for code in rutf8.Utf8StringIterator(text):
        if not identifier_continue(code):
            return False
    return True


def layout(code):
    return unicodedb.isspace(code)


def unicode_solo(code):
    # SWI's newer syntax keeps non-ASCII symbols and these punctuation
    # categories separate. Identifier recognition takes precedence.
    if code < 128:
        return False
    category = unicodedb.category(code)
    return category.startswith('S') or category in ('Pc', 'Pd', 'Po')


def ascii_graphic(code):
    return code < 128 and chr(code) in '#$&*+-./:<=>?@^~\\'
