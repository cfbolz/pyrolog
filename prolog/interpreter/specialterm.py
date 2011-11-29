from prolog.interpreter import term
from prolog.interpreter import signature

from pypy.rlib import jit, objectmodel, rarithmetic

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
    pass

class AnyArgumentDescr(ArgumentDescr):
    pass
class VarArgumentDescr(ArgumentDescr):
    pass
class NumberArgumentDescr(ArgumentDescr):
    pass
ANY_ARGUMENT = AnyArgumentDescr()
VAR_ARGUMENT = VarArgumentDescr()
NUMBER_ARGUMENT = NumberArgumentDescr()

class Shape(object):
    _immutable_fields_ = ["signature", "args[*]"]

    def __init__(self, signature, args, cache):
        self.signature = signature
        self.args = args
        self.cache = cache

    def argument_at(self, i, t):
        return self.args[i].read_argument(i, t)

def get_shape(signature, args):
    cache = signature.get_extra("shape")
    if cache is None:
        cache = ShapeCache(signature)
        signature.set_extra("shape", cache)
    argshapes = [ANY_ARGUMENT] * len(args)
    for i in range(len(args)):
        arg = args[i]
        if isinstance(arg, term.BindingVar):
            argshapes[i] = VAR_ARGUMENT
        elif isinstance(arg, term.Number):
            argshapes[i] = NUMBER_ARGUMENT
    return cache.get(argshapes)

class SpecialTerm(term.Callable):
    def __init__(self, signature, args):
        self.shape = get_shape(signature, args)

    def get_shape(self):
        return jit.promote(self.shape)

    def name(self):
        return self.signature().name

    def signature(self):
        return self.get_shape().signature

    def argument_at(self, i):
        raise NotImplementedError("abstract base")

    def argument_count(self):
        raise NotImplementedError("abstract base")


