import py
import math
from prolog.interpreter.parsing import TermBuilder
from prolog.interpreter import helper, term, error
from prolog.interpreter.signature import Signature
from prolog.interpreter.error import UnificationFailed
from rpython.rlib.rarithmetic import ovfcheck_float_to_int
from rpython.rlib.unroll import unrolling_iterable
from rpython.rlib import jit, rarithmetic, objectmodel
from rpython.rlib.rbigint import rbigint

Signature.register_extr_attr("arithmetic")

def eval_arithmetic(engine, obj):
    result = obj.eval_arithmetic(engine)
    return make_int(result)

class CodeCollector(object):
    def __init__(self):
        self.code = []
        self.blocks = []

    def emit(self, line):
        for line in line.split("\n"):
            self.code.append(" " * (4 * len(self.blocks)) + line)

    def start_block(self, blockstarter):
        assert blockstarter.endswith(":")
        self.emit(blockstarter)
        self.blocks.append(blockstarter)

    def end_block(self, starterpart=""):
        block = self.blocks.pop()
        assert starterpart in block, "ended wrong block %s with %s" % (
            block, starterpart)

    def tostring(self):
        assert not self.blocks
        return "\n".join(self.code)


def wrap_builtin_operation(name, num_args):
    fcode = CodeCollector()
    fcode.start_block('def prolog_%s(engine, query):' % name)
    for i in range(num_args):
        fcode.emit('var%s = query.argument_at(%s).eval_arithmetic(engine)' % (i, i))
    if num_args == 1:
        fcode.emit('return var0.arith_%s()' % name)
    elif num_args == 2:
        fcode.emit('return var0.arith_%s(var1)' % name)
    fcode.end_block('def')
    miniglobals = globals().copy()
    exec py.code.Source(fcode.tostring()).compile() in miniglobals
    result = miniglobals['prolog_' + name]
    return result

# remove unneeded parts, use sane names for operations
simple_functions = [
    ("+", 2, "add"),
    ("+", 1, "unaryadd"),
    ("-", 2, "sub"),
    ("-", 1, "unarysub"),
    ("*", 2, "mul"),
    ("/", 2, "div"),
    ("//", 2, "floordiv"),
    ("**", 2, "pow"),
    ("sqrt", 1, "sqrt"),
    (">>", 2, "shr"),
    ("<<", 2, "shl"),
    ("\\/", 2, "or"),
    ("/\\", 2, "and"),
    ("xor", 2, "xor"),
    ("mod", 2, "mod"),
    ("\\", 1, "not"),
    ("abs", 1, "abs"),
    ("max", 2, "max"),
    ("min", 2, "min"),
    ("round", 1, "round"),
    ("floor", 1, "floor"), #XXX
    ("ceiling", 1, "ceiling"), #XXX
    ("float", 1, "float"),
    ("float_fractional_part", 1, "float_fractional_part"), #XXX
    ("float_integer_part", 1, "float_integer_part")
]

for prolog_name, num_args, name in simple_functions:
    f = wrap_builtin_operation(name, num_args)
    
    signature = Signature.getsignature(prolog_name, num_args)
    signature.set_extra("arithmetic", f)

    for suffix in ["", "_number", "_bigint", "_float"]:
        def not_implemented_func(*args):
            raise NotImplementedError("abstract base class")
        setattr(term.Numeric, "arith_%s%s" % (name, suffix), not_implemented_func)

@jit.elidable_promote('all')
def get_arithmetic_function(signature):
    return signature.get_extra("arithmetic")

def make_int(w_value):
    if isinstance(w_value, term.BigInt):
        try:
            num = w_value.value.toint()
        except OverflowError:
            pass
        else:
            return term.Number(num)
    return w_value


def bigint_to_float(value):
    try:
        return value.tofloat()
    except OverflowError:
        error.throw_evaluation_error("float_overflow")


UNORDERED = 2


def integer_value(value):
    if isinstance(value, term.Number):
        return rbigint.fromint(value.num)
    assert isinstance(value, term.BigInt)
    return value.value


def compare_integer_float(integer, value):
    # Unlike standard term ordering, arithmetic comparisons equate 1 and 1.0.
    # NaNs are handled by compare_numbers before reaching this helper.
    if math.isinf(value):
        return -1 if value > 0.0 else 1
    if isinstance(integer, term.Number):
        # As in PyPy, small machine integers can be converted without rounding.
        if rarithmetic.LONG_BIT <= 32 or -1 <= integer.num >> 48 < 1:
            return term.rcmp(float(integer.num), value)
    truncated = rbigint.fromfloat(value)
    result = term.bigint_cmp(integer_value(integer), truncated)
    if result:
        return result
    if value != math.floor(value):
        return -1 if value > 0.0 else 1
    return 0


def compare_numbers(left, right):
    if isinstance(left, term.Float):
        if math.isnan(left.floatval):
            return UNORDERED
        if isinstance(right, term.Float):
            if math.isnan(right.floatval):
                return UNORDERED
            return term.rcmp(left.floatval, right.floatval)
        return -compare_integer_float(right, left.floatval)
    if isinstance(right, term.Float):
        if math.isnan(right.floatval):
            return UNORDERED
        return compare_integer_float(left, right.floatval)
    if isinstance(left, term.Number) and isinstance(right, term.Number):
        return term.rcmp(left.num, right.num)
    return term.bigint_cmp(integer_value(left), integer_value(right))


def shift_count(value, left_shift):
    if isinstance(value, term.Number):
        if value.num < 0:
            error.throw_domain_error("not_less_than_zero", value)
        return value.num
    if isinstance(value, term.BigInt):
        if value.value.get_sign() < 0:
            error.throw_domain_error("not_less_than_zero", value)
        try:
            return value.value.toint()
        except OverflowError:
            if left_shift:
                error.throw_representation_error("shift_count")
            # Every representable integer has fewer bits than this count.
            return rarithmetic.maxint
    error.throw_type_error("integer", value)


def check_finite_float(value):
    if math.isinf(value):
        error.throw_evaluation_error("float_overflow")
    if math.isnan(value):
        error.throw_evaluation_error("undefined")


def make_float(value):
    # Check at each arithmetic operation, including intermediate results.
    # Float itself also represents terms constructed outside arithmetic.
    check_finite_float(value)
    return term.Float(value)


def float_pow(base, exponent):
    if base == 0.0 and exponent < 0.0:
        error.throw_evaluation_error("zero_divisor")
    try:
        result = math.pow(base, exponent)
    except ValueError:
        raise error.throw_evaluation_error("undefined")
    except OverflowError:
        raise error.throw_evaluation_error("float_overflow")
    return make_float(result)


def bigint_pow(base, exponent):
    if exponent.get_sign() < 0:
        return float_pow(bigint_to_float(base), bigint_to_float(exponent))
    return make_int(term.BigInt(base.pow(exponent)))


@jit.look_inside_iff(lambda base, exponent: jit.isconstant(exponent))
def int_pow(base, exponent):
    # As in PyPy's _pow_nomod: only unroll for a constant exponent.
    assert exponent >= 0
    result = 1
    while exponent:
        if exponent & 1:
            # The JIT requires a local exception edge for checked operations.
            try:
                result = rarithmetic.ovfcheck(result * base)
            except OverflowError:
                raise
        exponent >>= 1
        if exponent:
            try:
                base = rarithmetic.ovfcheck(base * base)
            except OverflowError:
                raise
    return result

@objectmodel.dont_inline
def rbigint_lshift(value, count):
    # work around the always_inline annotation for lshift, which clashes with
    # exception handling in arith_shl
    return value.lshift(count)

class __extend__(term.Numeric):
    def arith_sqrt(self):
        return self.arith_pow(term.Float(0.5))

    def arith_shl(self, other):
        if not isinstance(self, term.Number) and not isinstance(self, term.BigInt):
            error.throw_type_error("integer", self)
        count = shift_count(other, True)
        try:
            if isinstance(self, term.Number):
                if count < rarithmetic.LONG_BIT:
                    try:
                        return term.Number(rarithmetic.ovfcheck(self.num << count))
                    except OverflowError:
                        pass
                return make_int(term.BigInt(
                    rbigint.lshift_int_int_bigint_result(self.num, count)))
            assert isinstance(self, term.BigInt)
            return make_int(term.BigInt(rbigint_lshift(self.value, count)))
        except MemoryError:
            error.throw_resource_error("memory")

    def arith_shr(self, other):
        if not isinstance(self, term.Number) and not isinstance(self, term.BigInt):
            error.throw_type_error("integer", self)
        count = shift_count(other, False)
        if isinstance(self, term.Number):
            if count >= rarithmetic.LONG_BIT:
                return term.Number(-1 if self.num < 0 else 0)
            return term.Number(self.num >> count)
        assert isinstance(self, term.BigInt)
        return make_int(term.BigInt(self.value.rshift(count)))

class __extend__(term.Number):
    def arith_float(self):
        return make_float(float(self.num))

    # ------------------ addition ------------------ 
    def arith_add(self, other):
        return other.arith_add_number(self.num)

    def arith_add_number(self, other_num):
        try:
            res = rarithmetic.ovfcheck(other_num + self.num)
        except OverflowError:
            return self.arith_add_bigint(rbigint.fromint(other_num))
        return term.Number(res)

    def arith_add_bigint(self, other_value):
        return make_int(term.BigInt(other_value.add(rbigint.fromint(self.num))))
    def arith_add_float(self, other_float):
        return make_float(other_float + float(self.num))

    def arith_unaryadd(self):
        return self

    # ------------------ subtraction ------------------ 
    def arith_sub(self, other):
        return other.arith_sub_number(self.num)

    def arith_sub_number(self, other_num):
        try:
            res = rarithmetic.ovfcheck(other_num - self.num)
        except OverflowError:
            return self.arith_sub_bigint(rbigint.fromint(other_num))
        return term.Number(res)

    def arith_sub_bigint(self, other_value):
        return make_int(term.BigInt(other_value.sub(rbigint.fromint(self.num))))

    def arith_sub_float(self, other_float):
        return make_float(other_float - float(self.num))

    def arith_unarysub(self):
        try:
            res = rarithmetic.ovfcheck(-self.num)
        except OverflowError:
            return term.BigInt(rbigint.fromint(self.num).neg())
        return term.Number(res)


    # ------------------ multiplication ------------------ 
    def arith_mul(self, other):
        return other.arith_mul_number(self.num)

    def arith_mul_number(self, other_num):
        try:
            res = rarithmetic.ovfcheck(other_num * self.num)
        except OverflowError:
            return self.arith_mul_bigint(rbigint.fromint(other_num))
        return term.Number(res)

    def arith_mul_bigint(self, other_value):
        return make_int(term.BigInt(other_value.mul(rbigint.fromint(self.num))))

    def arith_mul_float(self, other_float):
        return make_float(other_float * float(self.num))

    # ------------------ division ------------------ 
    def arith_div(self, other):
        return other.arith_div_number(self.num)

    def arith_div_number(self, other_num):
        if self.num == 0:
            error.throw_evaluation_error("zero_divisor")
        try:
            res = rarithmetic.ovfcheck(other_num / self.num)
        except OverflowError:
            return self.arith_div_bigint(rbigint.fromint(other_num))
        return term.Number(res)

    def arith_div_bigint(self, other_value):
        if self.num == 0:
            error.throw_evaluation_error("zero_divisor")
        return make_int(term.BigInt(other_value.div(rbigint.fromint(self.num))))

    def arith_div_float(self, other_float):
        if self.num == 0:
            error.throw_evaluation_error("zero_divisor")
        return make_float(other_float / float(self.num))

    def arith_floordiv(self, other):
        return other.arith_floordiv_number(self.num)

    def arith_floordiv_number(self, other_num):
        if self.num == 0:
            error.throw_evaluation_error("zero_divisor")
        try:
            res = rarithmetic.ovfcheck(other_num // self.num)
        except OverflowError:
            return self.arith_floordiv_bigint(rbigint.fromint(other_num))
        return term.Number(res)

    def arith_floordiv_bigint(self, other_value):
        if self.num == 0:
            error.throw_evaluation_error("zero_divisor")
        return make_int(term.BigInt(other_value.floordiv(rbigint.fromint(self.num))))

    def arith_floordiv_float(self, other_float):
        error.throw_type_error("integer", other_float)


    # ------------------ power ------------------ 
    def arith_pow(self, other):
        return other.arith_pow_number(self.num)

    def arith_pow_number(self, other_num):
        if self.num < 0:
            return float_pow(float(other_num), float(self.num))
        try:
            result = int_pow(other_num, self.num)
        except OverflowError:
            return self.arith_pow_bigint(rbigint.fromint(other_num))
        return term.Number(result)

    def arith_pow_bigint(self, other_value):
        if self.num < 0:
            return float_pow(bigint_to_float(other_value), float(self.num))
        return make_int(term.BigInt(other_value.int_pow(self.num)))

    def arith_pow_float(self, other_float):
        return float_pow(other_float, float(self.num))

    # ------------------ or ------------------ 
    def arith_or(self, other):
        return other.arith_or_number(self.num)

    def arith_or_number(self, other_num):
        return term.Number(other_num | self.num)

    def arith_or_bigint(self, other_value):
        return make_int(term.BigInt(rbigint.fromint(self.num).or_(other_value)))

    # ------------------ and ------------------ 
    def arith_and(self, other):
        return other.arith_and_number(self.num)

    def arith_and_number(self, other_num):
        return term.Number(other_num & self.num)

    def arith_and_bigint(self, other_value):
        return make_int(term.BigInt(rbigint.fromint(self.num).and_(other_value)))

    # ------------------ xor ------------------ 
    def arith_xor(self, other):
        return other.arith_xor_number(self.num)

    def arith_xor_number(self, other_num):
        return term.Number(other_num ^ self.num)

    def arith_xor_bigint(self, other_value):
        return make_int(term.BigInt(rbigint.fromint(self.num).xor(other_value)))

    # ------------------ mod ------------------ 
    def arith_mod(self, other):
        return other.arith_mod_number(self.num)

    def arith_mod_number(self, other_num):
        if self.num == 0:
            error.throw_evaluation_error("zero_divisor")
        return term.Number(other_num % self.num)

    def arith_mod_bigint(self, other_value):
        if self.num == 0:
            error.throw_evaluation_error("zero_divisor")
        return make_int(term.BigInt(other_value.mod(rbigint.fromint(self.num))))

    # ------------------ inversion ------------------
    def arith_not(self):
        return term.Number(~self.num)


    # ------------------ abs ------------------
    def arith_abs(self):
        if self.num >= 0:
            return self
        return term.Number(0).arith_sub(self)

    # ------------------ max ------------------
    def arith_max(self, other):
        return other.arith_max_number(self.num)

    def arith_max_number(self, other_num):
        return term.Number(max(other_num, self.num))

    def arith_max_bigint(self, other_value):
        self_value = rbigint.fromint(self.num)
        if self_value.lt(other_value):
            return make_int(term.BigInt(other_value))
        return make_int(term.BigInt(self_value))

    def arith_max_float(self, other_float):
        return make_float(max(other_float, float(self.num)))

    # ------------------ min ------------------
    def arith_min(self, other):
        return other.arith_min_number(self.num)

    def arith_min_number(self, other_num):
        return term.Number(min(other_num, self.num))

    def arith_min_bigint(self, other_value):
        self_value = rbigint.fromint(self.num)
        if self_value.lt(other_value):
            return make_int(term.BigInt(self_value))
        return make_int(term.BigInt(other_value))

    def arith_min_float(self, other_float):
        return make_float(min(other_float, float(self.num)))

    # ------------------ miscellanous ------------------
    def arith_round(self):
        return self

    def arith_floor(self):
        return self

    def arith_ceiling(self):
        return self

    def arith_float_fractional_part(self):
        return term.Number(0)

    def arith_float_integer_part(self):
        return self


class __extend__(term.Float):    
    def arith_float(self):
        return self

    # Reject floats whether they are the left operand or receive a dispatched
    # integer operand. Keep separate signatures for RPython's argument types.
    def arith_or(self, other):
        error.throw_type_error("integer", self)

    def arith_or_number(self, other_num):
        error.throw_type_error("integer", self)

    def arith_or_bigint(self, other_value):
        error.throw_type_error("integer", self)

    def arith_or_float(self, other_float):
        error.throw_type_error("integer", self)

    arith_and = arith_xor = arith_mod = arith_or
    arith_and_number = arith_xor_number = arith_mod_number = arith_or_number
    arith_and_bigint = arith_xor_bigint = arith_mod_bigint = arith_or_bigint
    arith_and_float = arith_xor_float = arith_mod_float = arith_or_float

    def arith_not(self):
        error.throw_type_error("integer", self)

    # ------------------ addition ------------------ 
    def arith_add(self, other):
        return other.arith_add_float(self.floatval)

    def arith_add_number(self, other_num):
        return make_float(float(other_num) + self.floatval)

    def arith_add_bigint(self, other_value):
        return make_float(bigint_to_float(other_value) + self.floatval)

    def arith_add_float(self, other_float):
        return make_float(other_float + self.floatval)

    def arith_unaryadd(self):
        return self

    # ------------------ subtraction ------------------ 
    def arith_sub(self, other):
        return other.arith_sub_float(self.floatval)

    def arith_sub_number(self, other_num):
        return make_float(float(other_num) - self.floatval)

    def arith_sub_bigint(self, other_value):
        return make_float(bigint_to_float(other_value) - self.floatval)

    def arith_sub_float(self, other_float):
        return make_float(other_float - self.floatval)

    def arith_unarysub(self):
        return make_float(-self.floatval)

    # ------------------ multiplication ------------------ 
    def arith_mul(self, other):
        return other.arith_mul_float(self.floatval)

    def arith_mul_number(self, other_num):
        return make_float(float(other_num) * self.floatval)

    def arith_mul_bigint(self, other_value):
        return make_float(bigint_to_float(other_value) * self.floatval)

    def arith_mul_float(self, other_float):
        return make_float(other_float * self.floatval)

    # ------------------ division ------------------ 
    def arith_div(self, other):
        return other.arith_div_float(self.floatval)

    def arith_div_number(self, other_num):
        if self.floatval == 0.0:
            error.throw_evaluation_error("zero_divisor")
        return make_float(float(other_num) / self.floatval)

    def arith_div_bigint(self, other_value):
        if self.floatval == 0.0:
            error.throw_evaluation_error("zero_divisor")
        return make_float(bigint_to_float(other_value) / self.floatval)

    def arith_div_float(self, other_float):
        if self.floatval == 0.0:
            error.throw_evaluation_error("zero_divisor")
        return make_float(other_float / self.floatval)

    def arith_floordiv(self, other_float):
        error.throw_type_error("integer", self)
    def arith_floordiv_number(self, other_num):
        error.throw_type_error("integer", self)
    def arith_floordiv_bigint(self, other_value):
        error.throw_type_error("integer", self)
    def arith_floordiv_float(self, other_float):
        error.throw_type_error("integer", other_float)

    # ------------------ power ------------------ 
    def arith_pow(self, other):
        return other.arith_pow_float(self.floatval)

    def arith_pow_number(self, other_num):
        return float_pow(float(other_num), self.floatval)

    def arith_pow_bigint(self, other_value):
        return float_pow(bigint_to_float(other_value), self.floatval)

    def arith_pow_float(self, other_float):
        return float_pow(other_float, self.floatval)

    # ------------------ abs ------------------ 
    def arith_abs(self):
        return make_float(abs(self.floatval))

    # ------------------ max ------------------ 
    def arith_max(self, other):
        return other.arith_max_float(self.floatval)

    def arith_max_number(self, other_num):
        return make_float(max(float(other_num), self.floatval))

    def arith_max_bigint(self, other_value):
        return make_float(max(bigint_to_float(other_value), self.floatval))

    def arith_max_float(self, other_float):
        return make_float(max(other_float, self.floatval))
    
    # ------------------ min ------------------ 
    def arith_min(self, other):
        return other.arith_min_float(self.floatval)

    def arith_min_number(self, other_num):
        return make_float(min(float(other_num), self.floatval))

    def arith_min_bigint(self, other_value):
        return make_float(min(bigint_to_float(other_value), self.floatval))

    def arith_min_float(self, other_float):
        return make_float(min(other_float, self.floatval))

    # ------------------ miscellanous ------------------
    def arith_round(self):
        fval = self.floatval
        check_finite_float(fval)
        if fval >= 0:
            factor = 1
        else:
            factor = -1

        fval = fval * factor
        # Adding 0.5 first can round an already integral float up near 2**52.
        rounded = math.floor(fval)
        if fval - rounded >= 0.5:
            rounded += 1.0
        rounded *= factor
        try:
            val = ovfcheck_float_to_int(rounded)
        except OverflowError:
            return term.BigInt(rbigint.fromfloat(rounded))
        return term.Number(val)

    def arith_floor(self):
        check_finite_float(self.floatval)
        try:
            val = ovfcheck_float_to_int(math.floor(self.floatval))
        except OverflowError:
            return term.BigInt(rbigint.fromfloat(math.floor(self.floatval)))
        return term.Number(val)

    def arith_ceiling(self):
        check_finite_float(self.floatval)
        try:
            val = ovfcheck_float_to_int(math.ceil(self.floatval))
        except OverflowError:
            return term.BigInt(rbigint.fromfloat(math.ceil(self.floatval)))
        return term.Number(val)

    def arith_float_fractional_part(self):
        check_finite_float(self.floatval)
        try:
            val = ovfcheck_float_to_int(self.floatval)
        except OverflowError:
            val = rbigint.fromfloat(self.floatval).tofloat()
        return make_float(float(self.floatval - val))

    def arith_float_integer_part(self):
        check_finite_float(self.floatval)
        try:
            val = ovfcheck_float_to_int(self.floatval)
        except OverflowError:
            return term.BigInt(rbigint.fromfloat(self.floatval))
        return term.Number(val)


class __extend__(term.BigInt):
    def arith_float(self):
        return make_float(bigint_to_float(self.value))

    # ------------------ addition ------------------ 
    def arith_add(self, other):
        return other.arith_add_bigint(self.value)

    def arith_add_number(self, other_num):
        return make_int(term.BigInt(rbigint.fromint(other_num).add(self.value)))

    def arith_add_bigint(self, other_value):
        return make_int(term.BigInt(other_value.add(self.value)))

    def arith_add_float(self, other_float):
        return make_float(other_float + bigint_to_float(self.value))

    def arith_unaryadd(self):
        return self

    # ------------------ subtraction ------------------ 
    def arith_sub(self, other):
        return other.arith_sub_bigint(self.value)

    def arith_sub_number(self, other_num):
        return make_int(term.BigInt(rbigint.fromint(other_num).sub(self.value)))

    def arith_sub_bigint(self, other_value):
        return make_int(term.BigInt(other_value.sub(self.value)))

    def arith_sub_float(self, other_float):
        return make_float(other_float - bigint_to_float(self.value))

    def arith_unarysub(self):
        return term.BigInt(self.value.neg())

    # ------------------ multiplication ------------------ 
    def arith_mul(self, other):
        return other.arith_mul_bigint(self.value)

    def arith_mul_number(self, other_num):
        return make_int(term.BigInt(rbigint.fromint(other_num).mul(self.value)))

    def arith_mul_bigint(self, other_value):
        return make_int(term.BigInt(other_value.mul(self.value)))

    def arith_mul_float(self, other_float):
        return make_float(other_float * bigint_to_float(self.value))

    # ------------------ division ------------------ 
    def arith_div(self, other):
        return other.arith_div_bigint(self.value)

    def arith_div_number(self, other_num):
        return make_int(term.BigInt(rbigint.fromint(other_num).div(self.value)))

    def arith_div_bigint(self, other_value):
        try:
            return make_int(term.BigInt(other_value.div(self.value)))
        except ZeroDivisionError:
            error.throw_evaluation_error("zero_divisor")

    def arith_div_float(self, other_float):
        return make_float(other_float / bigint_to_float(self.value))

    def arith_floordiv(self, other):
        return other.arith_floordiv_bigint(self.value)

    def arith_floordiv_number(self, other_num):
        return make_int(term.BigInt(rbigint.fromint(other_num).div(self.value)))

    def arith_floordiv_bigint(self, other_value):
        try:
            return make_int(term.BigInt(other_value.div(self.value)))
        except ZeroDivisionError:
            error.throw_evaluation_error("zero_divisor")

    def arith_floordiv_float(self, other_float):
        error.throw_type_error("integer", other_float)
    # ------------------ power ------------------
    def arith_pow(self, other):
        return other.arith_pow_bigint(self.value)

    def arith_pow_number(self, other_num):
        return bigint_pow(rbigint.fromint(other_num), self.value)

    def arith_pow_bigint(self, other_value):
        return bigint_pow(other_value, self.value)

    def arith_pow_float(self, other_float):
        return float_pow(other_float, bigint_to_float(self.value))

    # ------------------ or ------------------ 
    def arith_or(self, other):
        return other.arith_or_bigint(self.value)

    def arith_or_number(self, other_num):
        return make_int(term.BigInt(rbigint.fromint(other_num).or_(self.value)))

    def arith_or_bigint(self, other_value):
        return make_int(term.BigInt(other_value.or_(self.value)))

    # ------------------ and ------------------ 
    def arith_and(self, other):
        return other.arith_and_bigint(self.value)

    def arith_and_number(self, other_num):
        return make_int(term.BigInt(rbigint.fromint(other_num).and_(self.value)))

    def arith_and_bigint(self, other_value):
        return make_int(term.BigInt(other_value.and_(self.value)))

    # ------------------ xor ------------------ 
    def arith_xor(self, other):
        return other.arith_xor_bigint(self.value)

    def arith_xor_number(self, other_num):
        return make_int(term.BigInt(rbigint.fromint(other_num).xor(self.value)))

    def arith_xor_bigint(self, other_value):
        return make_int(term.BigInt(other_value.xor(self.value)))

    # ------------------ mod ------------------ 
    def arith_mod(self, other):
        return other.arith_mod_bigint(self.value)

    def arith_mod_number(self, other_num):
        try:
            return make_int(term.BigInt(rbigint.fromint(other_num).mod(self.value)))
        except ZeroDivisionError:
            error.throw_evaluation_error("zero_divisor")

    def arith_mod_bigint(self, other_value):
        try:
            return make_int(term.BigInt(other_value.mod(self.value)))
        except ZeroDivisionError:
            error.throw_evaluation_error("zero_divisor")

    # ------------------ inversion ------------------ 
    def arith_not(self):
        return make_int(term.BigInt(self.value.invert()))


    # ------------------ abs ------------------
    def arith_abs(self):
        return make_int(term.BigInt(self.value.abs()))


    # ------------------ max ------------------
    def arith_max(self, other):
        return other.arith_max_bigint(self.value)

    def arith_max_number(self, other_num):
        other_value = rbigint.fromint(other_num)
        if other_value.lt(self.value):
            return make_int(term.BigInt(self.value))
        return make_int(term.BigInt(other_value))

    def arith_max_bigint(self, other_value):
        if other_value.lt(self.value):
            return make_int(term.BigInt(self.value))
        return make_int(term.BigInt(other_value))

    def arith_max_float(self, other_float):
        return make_float(max(other_float, bigint_to_float(self.value)))

    # ------------------ min ------------------
    def arith_min(self, other):
        return other.arith_min_bigint(self.value)

    def arith_min_number(self, other_num):
        other_value = rbigint.fromint(other_num)
        if other_value.lt(self.value):
            return make_int(term.BigInt(other_value))
        return make_int(term.BigInt(self.value))

    def arith_min_bigint(self, other_value):
        if other_value.lt(self.value):
            return make_int(term.BigInt(other_value))
        return make_int(term.BigInt(self.value))

    def arith_min_float(self, other_float):
        return make_float(min(other_float, bigint_to_float(self.value)))

    # ------------------ miscellanous ------------------
    def arith_round(self):
        return make_int(self)

    def arith_floor(self):
        return make_int(self)

    def arith_ceiling(self):
        return make_int(self)

    def arith_float_fractional_part(self):
        return term.Number(0)

    def arith_float_integer_part(self):
        return make_int(self)
