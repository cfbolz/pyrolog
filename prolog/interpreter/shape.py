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

class WrapShape(Shape):
    def __init__(self, w_obj):
        Shape.__init__(self)
        self.w_obj = w_obj

    def resolve(self, storage):
        return self.w_obj

class InStorageShape(Shape):
    def __init__(self, num):
        Shape.__init__(self)
        self.num = num

    def resolve(self, storage):
        return storage[self.num]

class SharingShape(Shape):
    def __init__(self, signature, children):
        Shape.__init__(self)
        self.signature = signature
        self.children = children

    def resolve(self, storage):
        return ShapedCallable(self, storage)

    def resolve_at(self, i, storage):
        return self.children[i].resolve(storage)

    @staticmethod
    def build_potentially_wrap(signature, children):
        unwrapped = []
        for child in children:
            if not isinstance(child, WrapShape):
                return SharingShape(signature, children)
            unwrapped.append(child.w_obj)
        return WrapShape(Callable.build(signature.name, unwrapped,
                                        signature=signature))

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

