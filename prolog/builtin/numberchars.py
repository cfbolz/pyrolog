import math
from prolog.interpreter import helper, term, error
from prolog.builtin.register import expose_builtin
from prolog.interpreter.term import Callable
from rpython.rlib.rstring import ParseStringError, ParseStringOverflowError
from rpython.rlib.rarithmetic import string_to_int
from rpython.rlib.rbigint import rbigint
from prolog.interpreter.helper import wrap_list

def num_to_list(num, codes=False):
    from prolog.interpreter.helper import wrap_list
    s = ""
    if isinstance(num, term.Number):
        s = str(num.num)
    elif isinstance(num, term.Float):
        s = str(num.floatval)
        exponent = s.find('e')
        if exponent >= 0 and '.' not in s:
            s = s[:exponent] + '.0' + s[exponent:]
    elif isinstance(num, term.BigInt):
        s = num.value.str()
    else:
        error.throw_type_error("number", num)
    if codes:
        return wrap_list([term.Number(ord(c)) for c in s])
    return wrap_list([Callable.build(c) for c in s])

def parse_number(chars):
    # Validate the complete decimal token before invoking host conversions.
    text = "".join(chars).lstrip()
    size = len(text)
    i = 0
    if i < size and text[i] in "+-":
        i += 1
    start = i
    while i < size and "0" <= text[i] <= "9":
        i += 1
    if i == start:
        error.throw_syntax_error("Illegal number")
    is_float = i < size and text[i] == "."
    if is_float:
        i += 1
        start = i
        while i < size and "0" <= text[i] <= "9":
            i += 1
        if i == start:
            error.throw_syntax_error("Illegal number")
        if i < size and text[i] in "eE":
            i += 1
            if i < size and text[i] in "+-":
                i += 1
            start = i
            while i < size and "0" <= text[i] <= "9":
                i += 1
            if i == start:
                error.throw_syntax_error("Illegal number")
    if i != size:
        error.throw_syntax_error("Illegal number")
    if not is_float:
        try:
            return term.Number(string_to_int(text))
        except ParseStringOverflowError:
            return term.BigInt(rbigint.fromdecimalstr(text))
        except ParseStringError:
            error.throw_syntax_error("Illegal number")
    try:
        value = float(text)
    except ValueError:
        raise error.throw_syntax_error("Illegal number")
    except OverflowError:
        raise error.throw_evaluation_error("float_overflow")
    if math.isinf(value):
        error.throw_evaluation_error("float_overflow")
    return term.Float(value)

@expose_builtin("number_chars", unwrap_spec=["obj", "obj"])
def impl_number_chars(engine, heap, num, charlist):
    number_convert(heap, num, charlist)


@expose_builtin("number_codes", unwrap_spec=["obj", "obj"])
def impl_number_codes(engine, heap, num, codelist):
    number_convert(heap, num, codelist, codes=True)


def number_convert(heap, num, charlist, codes=False):
    if not isinstance(num, term.Numeric) and not isinstance(num, term.Var):
        error.throw_type_error("number", num)
    chars = helper.unwrap_char_list(charlist, allow_partial=True, codes=codes)
    if chars is not None:
        parse_number(chars).unify(num, heap)
    elif isinstance(num, term.Var):
        error.throw_instantiation_error()
    else:
        num_to_list(num, codes=codes).unify(charlist, heap)
