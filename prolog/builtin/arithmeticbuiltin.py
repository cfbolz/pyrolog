import py
from prolog.interpreter import helper, term, error, continuation
from prolog.builtin.register import expose_builtin
# ___________________________________________________________________
# arithmetic

def check_natural_number(value):
    if isinstance(value, term.Var):
        return
    if isinstance(value, term.Number):
        negative = value.num < 0
    elif isinstance(value, term.BigInt):
        negative = value.value.get_sign() < 0
    else:
        error.throw_type_error('integer', value)
        return
    if negative:
        error.throw_domain_error('not_less_than_zero', value)


@expose_builtin("succ", unwrap_spec=["obj", "obj"])
def impl_succ(engine, heap, predecessor, successor):
    check_natural_number(predecessor)
    check_natural_number(successor)
    if isinstance(predecessor, term.Var):
        if isinstance(successor, term.Var):
            error.throw_instantiation_error()
        assert isinstance(successor, term.Numeric)
        if (isinstance(successor, term.Number) and successor.num == 0 or
                isinstance(successor, term.BigInt) and successor.value.get_sign() == 0):
            raise error.UnificationFailed
        predecessor.unify(successor.arith_sub(term.Number(1)), heap)
    else:
        assert isinstance(predecessor, term.Numeric)
        successor.unify(predecessor.arith_add(term.Number(1)), heap)


@continuation.make_failure_continuation
def continue_between(Choice, engine, scont, fcont, heap, lower, upper, var):
    if lower < upper:
        fcont = Choice(engine, scont, fcont, heap, lower + 1, upper, var)
        heap = heap.branch()
    var.unify(term.Number(lower), heap)
    return scont, fcont, heap

@expose_builtin("between", unwrap_spec=["int", "int", "obj"],
               handles_continuation=True)
def impl_between(engine, heap, lower, upper, varorint, scont, fcont):
    if isinstance(varorint, term.Var):
        if lower > upper:
            raise error.UnificationFailed
        return continue_between(engine, scont, fcont, heap,
                                lower, upper, varorint)
    else:
        integer = helper.unwrap_int(varorint)
        if not (lower <= integer <= upper):
            raise error.UnificationFailed
    return scont, fcont, heap

@expose_builtin("is", unwrap_spec=["raw", "arithmetic"])
def impl_is(engine, heap, var, num):
    var.unify(num, heap)

for ext, prolog, python in [("eq", "=:=", "=="),
                            ("ne", "=\\=", "!="),
                            ("lt", "<", "<"),
                            ("le", "=<", "<="),
                            ("gt", ">", ">"),
                            ("ge", ">=", ">=")]:
    exec py.code.Source("""
@expose_builtin(prolog, unwrap_spec=["arithmetic", "arithmetic"])
def impl_arith_%s(engine, heap, num1, num2):
    eq = False
    if isinstance(num1, term.Number):
        if isinstance(num2, term.Number):
            if not (num1.num %s num2.num):
                raise error.UnificationFailed()
            else:
                return
        n1 = num1.num
    else:
        assert isinstance(num1, term.Float)
        n1 = num1.floatval
    if isinstance(num2, term.Number):
        n2 = num2.num
    else:
        assert isinstance(num2, term.Float)
        n2 = num2.floatval
    eq = n1 %s n2
    if not eq:
        raise error.UnificationFailed()""" % (ext, python, python)).compile()
 
