from prolog.interpreter import term
from prolog.interpreter import signature

from pypy.rlib import jit, objectmodel, rarithmetic, rerased
from pypy.rlib.objectmodel import specialize

erase, unerase = rerased.new_erasing_pair("pyrolog-shape")

signature.Signature.register_extr_attr("shape")

def shape_eq(args1, args2):
    return args1 == args2

def shape_hash(args):
    x = 0x345678
    for item in args:
        y = objectmodel.compute_identity_hash(item)
        x = rarithmetic.intmask((1000003 * x) ^ y)
    return x

class ShapeCache(object):
    def __init__(self, signature):
        self.signature = signature
        self.d = objectmodel.r_dict(shape_eq, shape_hash)

    def get(self, argshapes):
        try:
            return self.d[argshapes]
        except KeyError:
            res = Shape(self.signature, argshapes, self)
            self.d[argshapes] = res
            return res

class ArgumentDescr(object):
    def compatible_with(self, obj):
        return False

    def read_argument(self, i, obj):
        res = unerase(obj._raw_argument_at(i))
        assert self.compatible_with(res)
        return res

    def write_argument(self, i, val, obj):
        assert self.compatible_with(val)
        obj._raw_set_argument_at(i, erase(val))

class AnyArgumentDescr(ArgumentDescr):
    def compatible_with(self, obj):
        return True

class VarArgumentDescr(ArgumentDescr):
    def compatible_with(self, obj):
        return isinstance(obj, term.BindingVar)

class NumberArgumentDescr(ArgumentDescr):
    def compatible_with(self, obj):
        if not isinstance(obj, term.Number):
            return False
        val = obj.num
        # bit sucky
        try:
            rerased.erase_int(val)
        except OverflowError:
            return False
        return True

    def read_argument(self, i, obj):
        res = rerased.unerase_int(obj._raw_argument_at(i))
        return term.Number(res)

    def write_argument(self, i, val, obj):
        assert isinstance(val, term.Number)
        res = rerased.erase_int(val.num)
        obj._raw_set_argument_at(i, res)

ANY_ARGUMENT = AnyArgumentDescr()
VAR_ARGUMENT = VarArgumentDescr()
NUMBER_ARGUMENT = NumberArgumentDescr()

class Shape(object):
    _immutable_fields_ = ["signature", "args[*]"]

    def __init__(self, signature, args, cache):
        self.signature = signature
        self.args = args
        self.cache = cache

    def argument_at(self, i, obj):
        return self.args[i].read_argument(i, obj)

    def set_argument_at(self, i, val, obj):
        return self.args[i].write_argument(i, val, obj)

def get_shape(signature, args):
    cache = signature.get_extra("shape")
    if cache is None:
        cache = ShapeCache(signature)
        signature.set_extra("shape", cache)
    argshapes = [ANY_ARGUMENT] * len(args)
    for i in range(len(args)):
        arg = args[i]
        if VAR_ARGUMENT.compatible_with(arg):
            argshapes[i] = VAR_ARGUMENT
        elif NUMBER_ARGUMENT.compatible_with(arg):
            argshapes[i] = NUMBER_ARGUMENT
    return cache.get(argshapes)

def build(signature, args):
    if len(args) <= len(specialized_term_classes):
        shape = get_shape(signature, args)
        return specialized_term_classes[len(args) - 1](shape, args)

def make_specialized_term_cls(n_args):
    from pypy.rlib.unroll import unrolling_iterable
    arg_iter = unrolling_iterable(range(n_args))
    base = term.Callable
    class generic_callable(base):
        TYPE_STANDARD_ORDER = term.Term.TYPE_STANDARD_ORDER

        _immutable_fields_ = ["shape"] + ["val_%d" % x for x in arg_iter]

        def __init__(self, shape, args):
            self.shape = shape
            self._init_values(args)

        def _init_values(self, args):
            if args is None:
                return
            for x in range(len(args)):
                self.set_argument_at(x, args[x])

        def _make_new(self):
            cls = mutable_version
            return cls(self.get_shape(), None)

        def get_shape(self):
            return jit.promote(self.shape)

        def signature(self):
            return self.get_shape().signature

        def arguments(self):
            result = [None] * n_args
            for x in range(n_args):
                result[x] = self.argument_at(x)
            return result

        def argument_count(self):
            return len(self.get_shape().args)

        def argument_at(self, i):
            return self.get_shape().argument_at(i, self)

        def set_argument_at(self, i, obj):
            self.get_shape().set_argument_at(i, obj, self)

        def _raw_argument_at(self, i):
            for x in arg_iter:
                if x == i:
                    return getattr(self, 'val_%d' % x)
            raise IndexError

        def _raw_set_argument_at(self, i, arg):
            for x in arg_iter:
                if x == i:
                    setattr(self, 'val_%d' % x, arg)
                    return
            raise IndexError

        def argument_count(self):
            return n_args

        @jit.look_inside_iff(lambda self, other, heap, occurs_check:
                jit.isvirtual(self) or jit.isvirtual(other) or
                jit.isconstant(self) or jit.isconstant(other))
        def basic_unify(self, other, heap, occurs_check):
            if not (isinstance(other, generic_callable) and
                    self.get_shape() is other.get_shape()):
                return term.Callable.basic_unify(self, other, heap, occurs_check)
            for x in arg_iter:
                a = self.argument_at(x)
                b = other.argument_at(x)
                a.unify(b, heap, occurs_check)

    generic_callable.__name__ = 'SpecializedGeneric'+str(n_args)
    return generic_callable

specialized_term_classes = [make_specialized_term_cls(i) for i in range(1, 10)]
