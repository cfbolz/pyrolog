from pypy.rlib import jit, objectmodel, debug
from prolog.interpreter.term import Callable
# a Callable implementation that tries to save memory

class Shape(object):
    def __init__(self):
        pass

    def resolve(self, storage):
        raise NotImplementedError("abstract base class")

    def resolve_at(self, argnum, storage):
        w_obj = self.resolve(storage)
        if isinstance(w_obj, Callable):
            return w_obj.argument_at(argnum)
        raise TypeError

    def _compute_new_shape(self, memo):
        raise NotImplementedError("abstract base class")

    from prolog.interpreter.continuation import _dot

class WrapShape(Shape):
    _immutable_fields_ = ["w_obj"]
    def __init__(self, w_obj):
        Shape.__init__(self)
        self.w_obj = w_obj

    def resolve(self, storage):
        return self.w_obj

    def _compute_new_shape(self, memo):
        return self

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.w_obj)

class InStorageShape(Shape):
    _immutable_fields_ = ["num"]
    _cache = {}

    def __init__(self, num):
        Shape.__init__(self)
        self.num = num

    @staticmethod
    def build(num):
        res = InStorageShape._cache.get(num, None)
        if res is None:
            InStorageShape._cache[num] = res = InStorageShape(num)
        return res

    def resolve(self, storage):
        return storage[self.num]

    def _compute_new_shape(self, memo):
        num = memo.setdefault(self.num, len(memo))
        if num == self.num:
            return self
        return InStorageShape.build(num)

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.num)

def shape_eq((sig1, children1), (sig2, children2)):
    return sig1 is sig2 and children1 == children2

def shape_hash((sig, children)):
    from pypy.rlib.rarithmetic import intmask
    x = objectmodel.compute_identity_hash(sig)
    for item in children:
        y = objectmodel.compute_identity_hash(item)
        x = intmask((1000003 * x) ^ y)
    return x

class SharingShape(Shape):
    _immutable_fields_ = ["signature", "children[*]", "reshaper"]
    _cache = objectmodel.r_dict(shape_eq, shape_hash)

    transitions = None

    def __init__(self, signature, children):
        Shape.__init__(self)
        self.signature = signature
        self.children = children
        children = debug.make_sure_not_resized(children)
        self.reshaper = make_reshaper(self)

    @staticmethod
    def build(signature, children):
        key = signature, children
        res = SharingShape._cache.get(key, None)
        if res is None:
            SharingShape._cache[key] = res = SharingShape(signature, children)
        return res

    def _get_transition(self, i, shape):
        if self.transitions is None:
            return None
        return self.transitions.get((i, shape))

    def resolve(self, storage):
        if self.reshaper is not None:
            return self.reshaper.reshape(storage)
        else:
            return ShapedCallable(self, storage)

    def resolve_at(self, i, storage):
        return self.children[i].resolve(storage)

    @staticmethod
    def build_potentially_wrap(signature, children):
        unwrapped = [None] * len(children)
        for i in range(len(children)):
            child = children[i]
            if not isinstance(child, WrapShape):
                return SharingShape.build(signature, children)
            unwrapped[i] = child.w_obj
        return WrapShape(Callable.build(signature.name, unwrapped,
                                        signature=signature))

    def _compute_new_shape(self, memo):
        children = [None] * len(self.children)
        reuse = True
        for i in range(len(self.children)):
            child = self.children[i]._compute_new_shape(memo)
            children[i] = child
            reuse = reuse and child is self.children[i]
        if reuse:
            return self
        return SharingShape.build(self.signature, children)

    def __repr__(self):
        return "%s(%r, %r)" % (self.__class__.__name__, self.signature, self.children)

    def _dot(self, seen):
        if self in seen:
            return
        for line in Shape._dot(self, seen):
            yield line
        for i, child in enumerate(self.children):
            yield "%s -> %s [label=%s]" % (id(self), id(child), i)
            for line in child._dot(seen):
                yield line


def make_reshaper(shape):
    memo = {}
    newshape = shape._compute_new_shape(memo)
    if newshape is shape:
        return None
    storage_shaper = [-1] * len(memo)
    for key, value in memo.iteritems():
        storage_shaper[value] = key
    return Reshaper(storage_shaper, newshape)

class Reshaper(object):
    _immutable_fields_ = ["newshape", "storage_shaper[*]"]
    def __init__(self, storage_shaper, newshape):
        assert newshape.reshaper is None
        self.newshape = newshape
        storage_shaper = debug.make_sure_not_resized(storage_shaper)
        self.storage_shaper = storage_shaper

    def reshape(self, storage):
        newstorage = [None] * len(self.storage_shaper)
        for i in range(len(self.storage_shaper)):
            newstorage[i] = storage[self.storage_shaper[i]]
        return ShapedCallable(self.newshape, newstorage)


# _____________________________________________________________________

class ShapedCallable(Callable):
    _immutable_fields_ = ["shape", "storage[*]"]
    def __init__(self, shape, storage):
        assert isinstance(shape, SharingShape)
        self.shape = shape
        storage = debug.make_sure_not_resized(storage)
        self.storage = storage

    def signature(self):
        return self.shape.signature

    def argument_at(self, i):
        return self.shape.resolve_at(i, self.storage)

    def argument_count(self):
        return self.shape.signature.numargs

    @objectmodel.specialize.arg(3)
    def basic_unify(self, other, heap, occurs_check=False):
        if (isinstance(other, ShapedCallable) and
                self.shape is other.shape):
            for i in range(len(self.storage)):
                self.storage[i].unify(other.storage[i], heap, occurs_check)
            return
        return Callable.basic_unify(self, other, heap, occurs_check)
# _____________________________________________________________________

def term_with_numbered_vars_to_shape(w_obj):
    from prolog.interpreter import term
    if isinstance(w_obj, term.NumberedVar):
        return InStorageShape.build(w_obj.num)
    elif isinstance(w_obj, Callable):
        argshapes = [term_with_numbered_vars_to_shape(w_arg)
                        for w_arg in w_obj.arguments()]
        return SharingShape.build_potentially_wrap(w_obj.signature(), argshapes)
    return WrapShape(w_obj)

@jit.unroll_safe
def build(shape, args):
    assert len(args) != 0
    assert len(shape.children) == len(args)
    storage = []
    shapeargs = []
    storeindex = 0
    for i in range(len(args)):
        arg = args[i]
        if isinstance(arg, ShapedCallable):
            newshape = shape._get_transition(storeindex, arg.shape)
            if newshape:
                storeindex += len(arg.storage)
                shapeargs += arg.storage
                shape = newshape
                continue
        shapeargs.append(InStorageShape.build(storeindex))
        storeindex += 1
        shapeargs.append(arg)
    return ShapedCallable(shape, shapeargs)


# _____________________________________________________________________

