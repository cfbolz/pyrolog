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


def parse_integer_literal(s):
    from prolog.interpreter.term import Number, BigInt
    base = 10
    if s.startswith('0x'):
        base = 16
    elif s.startswith('0o'):
        base = 8
    elif s.startswith('0b'):
        base = 2
    try:
        return Number(string_to_int(s, base))
    except ParseStringOverflowError:
        return BigInt(rbigint.fromstr(s, base))


def unescape(s, quote="'"):
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
            if i == len(s):
                error.throw_syntax_error("character_escape")
            c = s[i]
            i += 1
            if c in 'uU':
                count = 4 if c == 'u' else 8
                if i + count > len(s):
                    error.throw_syntax_error("character_escape")
                value = 0
                for j in range(count):
                    digit = s[i + j].lower()
                    if digit not in '0123456789abcdef':
                        error.throw_syntax_error("character_escape")
                    value = value * 16 + '0123456789abcdef'.find(digit)
                i += count
                try:
                    result.append(rutf8.unichr_as_utf8(value))
                except rutf8.OutOfRange:
                    error.throw_syntax_error("character_code")
            elif c == 'x' or '0' <= c <= '7':
                base = 16 if c == 'x' else 8
                value = 0 if c == 'x' else ord(c) - 48
                digits = 0 if c == 'x' else 1
                while i < len(s) and s[i] != "\\":
                    digit = '0123456789abcdef'.find(s[i].lower())
                    if digit < 0 or digit >= base or value > 0x10ffff:
                        error.throw_syntax_error("character_escape")
                    value = value * base + digit
                    digits += 1
                    i += 1
                if i == len(s) or digits == 0:
                    error.throw_syntax_error("character_escape")
                i += 1
                try:
                    result.append(rutf8.unichr_as_utf8(value))
                except rutf8.OutOfRange:
                    error.throw_syntax_error("character_code")
            elif c == "\n":
                pass
            elif c in "'\"":
                result.append(c)
            elif "\\" + c in ESCAPES:
                result.append(ESCAPES["\\" + c])
            else:
                error.throw_syntax_error("character_escape")
    return "".join(result)

