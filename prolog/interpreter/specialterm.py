from prolog.interpreter import term
from prolog.interpreter import signature

from pypy.rlib import jit

signature.Signature.register_extr_attr("shape")

class ShapeCache(object):
    def __init__(self, signature):
        self.signature = signature
        self.d = {}

    def get(self, argshapes):
        try:
            return self.d[tuple(argshapes)]
        except KeyError:
            res = Shape(self.signature, argshapes, self)
            self.d[tuple(argshapes)] = res
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


