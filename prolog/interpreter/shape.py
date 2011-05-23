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

class WrapShape(Shape):
    def __init__(self, w_obj):
        Shape.__init__(self)
        self.w_obj = w_obj

    def resolve(self, storage):
        return self.w_obj

    def _compute_new_shape(self, memo):
        return self

class InStorageShape(Shape):
    def __init__(self, num):
        Shape.__init__(self)
        self.num = num

    def resolve(self, storage):
        return storage[self.num]

    def _compute_new_shape(self, memo):
        num = memo.setdefault(self.num, len(memo))
        if num == self.num:
            return self
        return InStorageShape(num)

class SharingShape(Shape):
    def __init__(self, signature, children):
        Shape.__init__(self)
        self.signature = signature
        self.children = children
        self.reshaper = make_reshaper(self)

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
                return SharingShape(signature, children)
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
        return SharingShape(self.signature, children)


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
    def __init__(self, storage_shaper, newshape):
        assert newshape.reshaper is None
        self.newshape = newshape
        self.storage_shaper = storage_shaper

    def reshape(self, storage):
        newstorage = [None] * len(self.storage_shaper)
        for i in range(len(self.storage_shaper)):
            newstorage[i] = storage[self.storage_shaper[i]]
        return ShapedCallable(self.newshape, newstorage)


# _____________________________________________________________________

class ShapedCallable(Callable):
    def __init__(self, shape, storage):
        assert isinstance(shape, SharingShape)
        self.shape = shape
        self.storage = storage

    def signature(self):
        return self.shape.signature

    def argument_at(self, i):
        return self.shape.resolve_at(i, self.storage)

    def argument_count(self):
        return self.shape.signature.numargs

# _____________________________________________________________________

def term_with_numbered_vars_to_shape(w_obj):
    from prolog.interpreter import term
    if isinstance(w_obj, term.NumberedVar):
        return InStorageShape(w_obj.num)
    elif isinstance(w_obj, Callable):
        argshapes = [term_with_numbered_vars_to_shape(w_arg)
                        for w_arg in w_obj.arguments()]
        return SharingShape.build_potentially_wrap(w_obj.signature(), argshapes)
    return WrapShape(w_obj)

