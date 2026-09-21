from prolog.interpreter import term, error
from prolog.builtin.register import expose_builtin
from prolog.interpreter.term import Callable
from prolog.interpreter.term import specialized_term_classes
from rpython.rlib.rstring import ParseStringError, ParseStringOverflowError
from rpython.rlib.rarithmetic import ovfcheck, string_to_int
from rpython.rlib.rbigint import rbigint
from prolog.interpreter.signature import Signature
from prolog.interpreter.helper import wrap_list

conssig = Signature.getsignature(".", 2)
num_atom_names = [str(i) for i in range(10)]
digits = ["0", "1", "2", "3", "4",
          "5", "6", "7", "8", "9"]

def num_to_list(num):
    from prolog.interpreter.helper import wrap_list
    s = ""
    if isinstance(num, term.Number):
        s = str(num.num)
    elif isinstance(num, term.Float):
        s = str(num.floatval)
    elif isinstance(num, term.BigInt):
        s = num.value.str()
    else:
        error.throw_type_error("number", num)
    return wrap_list([Callable.build(c) for c in s])

def cons_to_num(charlist):
    from prolog.interpreter.helper import unwrap_char_list
    unwrapped = unwrap_char_list(charlist)
    numlist = []
    saw_dot = False
    first = True
    i = 0
    for digit in unwrapped:
        if first and len(digit) == 1 and digit.isspace():
            continue
        if digit not in digits:
            if digit == ".":
                if saw_dot or first or (i == 1 and numlist[0] == "-"):
                    error.throw_syntax_error("Illegal number")
                else:
                    saw_dot = True
            elif digit == "-":
                if not first:
                    error.throw_syntax_error("Illegal number")
            else:
                error.throw_syntax_error("Illegal number")
        numlist.append(digit)
        i += 1
        first = False
    
    if not numlist:
        error.throw_syntax_error("Illegal number")
    numstr = "".join(numlist)
    if numstr.find(".") == -1: # no float
        try:
            return term.Number(string_to_int(numstr))
        except ParseStringOverflowError:
            return term.BigInt(rbigint.fromdecimalstr(numstr))
        except ParseStringError:
            error.throw_syntax_error("Illegal number")
    try:
        return term.Float(float(numstr))
    except ValueError:
        error.throw_syntax_error("Illegal number")

@expose_builtin("number_chars", unwrap_spec=["obj", "obj"])
def impl_number_chars(engine, heap, num, charlist):
    if not isinstance(num, (term.Numeric, term.Var)):
        error.throw_type_error("number", num)
    if not isinstance(charlist, term.Var):
        cons_to_num(charlist).unify(num, heap)
    else:
        if isinstance(num, term.Var):
            error.throw_instantiation_error(num)
        else:
            num_to_list(num).unify(charlist, heap)
