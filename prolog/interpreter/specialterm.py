from prolog.interpreter import term
from prolog.interpreter import signature

from pypy.rlib import jit, objectmodel, rarithmetic, rerased, unroll
from pypy.rlib.objectmodel import specialize

erase, unerase = rerased.new_erasing_pair("pyrolog-shape")

signature.Signature.register_extr_attr("shape")

conssig = signature.Signature.getsignature(".", 2)

class ArgumentDescr(object):
    char = "b"
    def compatible_with(self, obj):
        return False

    def dereference_with_known_type(self, obj, heap):
        return obj.dereference(heap)

    def read_argument(self, i, obj):
        res = unerase(obj._raw_argument_at(i))
        return res

    def read_argument_dereference(self, i, obj, heap):
        res = self.read_argument(i, obj)
        return self.dereference_with_known_type(res, heap)

    def write_argument(self, i, val, obj):
        assert self.compatible_with(val)
        obj._raw_set_argument_at(i, erase(val))

class AnyArgumentDescr(ArgumentDescr):
    char = "*"
    def compatible_with(self, obj):
        return True

class VarArgumentDescr(ArgumentDescr):
    char = "X"
    def compatible_with(self, obj):
        return isinstance(obj, term.BindingVar)

    def dereference_with_known_type(self, obj, heap):
        assert isinstance(obj, term.BindingVar)
        return obj.dereference(heap)

    def read_argument(self, i, obj):
        res = unerase(obj._raw_argument_at(i))
        jit.record_known_class(res, term.BindingVar)
        return res

class NumberArgumentDescr(ArgumentDescr):
    char = "n"
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
all_argument_descrs = [VarArgumentDescr(),
                       NumberArgumentDescr()]

class Shape(object):
    _immutable_fields_ = ["signature", "args[*]"]

    def __init__(self, signature, args):
        self.signature = signature
        self.args = args
        self.str = "".join([a.char for a in args])
        self.cache = None

    def argument_at(self, i, obj):
        return self.args[i].read_argument(i, obj)

    def argument_at_dereference(self, i, obj, heap):
        return self.args[i].read_argument_dereference(i, obj, heap)

    def set_argument_at(self, i, val, obj):
        return self.args[i].write_argument(i, val, obj)

    @jit.elidable
    def replace(self, i, arg):
        if self.args[i] is arg:
            return self
        key = (i, arg)
        if self.cache is None:
            self.cache = {}
        elif key in self.cache:
            return self.cache[key]
        args = self.args[:i] + [arg] + self.args[i + 1:]
        shape = Shape(self.signature, args)
        self.cache[key] = shape
        return shape

@jit.elidable
def get_base_shape(signature):
    shape = signature.get_extra("shape")
    if shape is None:
        shape = Shape(signature, [ANY_ARGUMENT] * signature.numargs)
        signature.set_extra("shape", shape)
    return shape

@jit.unroll_safe
def get_shape(signature, args):
    shape = get_base_shape(signature)
    for i in range(len(args)):
        arg = args[i]
        for descr in all_argument_descrs:
            if descr.compatible_with(arg):
                argshape = descr
                break
        else:
            continue
        shape = shape.replace(i, argshape)
    return shape

def build(signature, args):
    shape = get_shape(signature, args)
    if signature.eq(conssig):
        return Cons(shape, args)
    if len(args) <= len(specialized_term_classes):
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
            for x in arg_iter:
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

        def argument_at_dereference(self, i, heap):
            return self.get_shape().argument_at_dereference(i, self, heap)

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


    generic_callable.__name__ = 'SpecializedGeneric'+str(n_args)
    return generic_callable

specialized_term_classes = [make_specialized_term_cls(i) for i in range(1, 10)]

class Cons(make_specialized_term_cls(2)):
    def name(self):
        return "."

    def signature(self):
        return conssig

    def _make_new(self, name, signature):
        return Cons(name, None, signature)

def make_specialized_argument_descr(termcls):
    class cls(ArgumentDescr):
        def compatible_with(self, obj):
            return isinstance(obj, termcls)

        def dereference_with_known_type(self, obj, heap):
            return obj

        def read_argument(self, i, obj):
            res = unerase(obj._raw_argument_at(i))
            jit.record_known_class(res, termcls)
            return res
    cls.__name__ = termcls.__name__ + "ArgumentDescr"
    return cls()

def make_arg_descrs():
    for i, cls in enumerate(specialized_term_classes):
        descr = make_specialized_argument_descr(cls)
        descr.char = str(i + 1)
        assert len(descr.char) == 1
        all_argument_descrs.append(descr)
    all_argument_descrs.append(make_specialized_argument_descr(term.Atom))
    all_argument_descrs[-1].char = "a"
    all_argument_descrs.append(make_specialized_argument_descr(Cons))
    all_argument_descrs[-1].char = "."
make_arg_descrs()

all_argument_descrs = unroll.unrolling_iterable(all_argument_descrs)

