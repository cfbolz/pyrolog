"""Literal decoding shared by the parser and numeric conversions."""
from rpython.rlib import rutf8
from rpython.rlib.rstring import ParseStringOverflowError
from rpython.rlib.rarithmetic import string_to_int
from rpython.rlib.rbigint import rbigint
from prolog.interpreter import error


ESCAPES = {
    "\\a": "\a",
    "\\b": "\b",
    "\\f": "\f",
    "\\n": "\n",
    "\\r": "\r",
    "\\t": "\t",
    "\\v": "\v",
    "\\\\":  "\\"
}


def integer_literal_base(s):
    start = 0
    if s and s[0] in '+-':
        start = 1
    prefix = s[start:start + 2]
    if prefix == '0x':
        return 16
    if prefix == '0o':
        return 8
    if prefix == '0b':
        return 2
    return 10


def parse_integer_literal(s):
    from prolog.interpreter.term import Number, BigInt
    base = integer_literal_base(s)
    try:
        return Number(string_to_int(s, base))
    except ParseStringOverflowError:
        return BigInt(rbigint.fromstr(s, base))


class EscapeError(Exception):
    def __init__(self, start, end, reason):
        self.start = start
        self.end = end
        self.reason = reason


def _escape_error(s, start, end, reason='character_escape'):
    # An invalid non-ASCII escape/digit must still have a whole-code-point span.
    while end < len(s) and ord(s[end]) & 0xc0 == 0x80:
        end += 1
    raise EscapeError(start, end, reason)


def unescape(s, quote="'"):
    try:
        return unescape_literal(s, quote)
    except EscapeError as exc:
        raise error.throw_syntax_error(exc.reason)


def unescape_literal(s, quote="'"):
    result = []
    i = 0
    while i < len(s):
        c = s[i]
        i += 1
        if c == quote and i < len(s) and s[i] == quote:
            result.append(c)
            i += 1
        elif c != "\\":
            result.append(c)
        else:
            start = i - 1
            if i == len(s):
                _escape_error(s, start, i)
            c = s[i]
            i += 1
            if c in 'uU':
                count = 4 if c == 'u' else 8
                if i + count > len(s):
                    _escape_error(s, start, len(s))
                value = 0
                for j in range(count):
                    digit = s[i + j].lower()
                    if digit not in '0123456789abcdef':
                        _escape_error(s, start, i + j + 1)
                    value = value * 16 + '0123456789abcdef'.find(digit)
                i += count
                try:
                    result.append(rutf8.unichr_as_utf8(value))
                except rutf8.OutOfRange:
                    _escape_error(s, start, i, 'character_code')
            elif c == 'x' or '0' <= c <= '7':
                base = 16 if c == 'x' else 8
                value = 0 if c == 'x' else ord(c) - 48
                digits = 0 if c == 'x' else 1
                while i < len(s) and s[i] != "\\":
                    digit = '0123456789abcdef'.find(s[i].lower())
                    if digit < 0 or digit >= base or value > 0x10ffff:
                        _escape_error(s, start, i + 1)
                    value = value * base + digit
                    digits += 1
                    i += 1
                if i == len(s) or digits == 0:
                    _escape_error(s, start, i)
                i += 1
                try:
                    result.append(rutf8.unichr_as_utf8(value))
                except rutf8.OutOfRange:
                    _escape_error(s, start, i, 'character_code')
            elif c == "\n":
                pass
            elif c in "'\"":
                result.append(c)
            elif "\\" + c in ESCAPES:
                result.append(ESCAPES["\\" + c])
            else:
                _escape_error(s, start, i)
    return "".join(result)
