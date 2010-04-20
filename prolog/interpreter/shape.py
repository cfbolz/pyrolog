from prolog.interpreter.term import Callable
# a Callable implementation that tries to save memory

class Shape(object):
    def resolve_at(self, argnum, storage):
        raise NotImplementedError("abstract base class")
    def resolve(self, storage):
        raise NotImplementedError("abstract base class")

class WrapShape(Shape):
    def __init__(self, w_obj):
        self.w_obj = w_obj

    def resolve(self, storage):
        return self.w_obj

class InStorageShape(Shape):
    def __init__(self, num):
        self.num = num

    def resolve(self, storage):
        return storage[self.num]

class SharingShape(Shape):
    def __init__(self, signature, children):
        self.signature = signature
        self.children = children

    def resolve(self, storage):
        return ShapedCallable(self, storage)

    def resolve_at(self, i, storage):
        return self.children[i].resolve(storage)

class ShapedCallable(Callable):
    def __init__(self, shape, storage):
        assert isinstance(shape, SharingShape)
        self.shape = shape
        self.storage = storage

    def signature(self):
        return self.shape.signature

    def argument_at(self, i):
        return self.shape.resolve_at(i, self.storage)
