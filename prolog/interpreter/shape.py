from pypy.rlib import jit, objectmodel, debug
from prolog.interpreter import term
# a Callable implementation that tries to save memory

# XXX tune this
MAX_DEPTH = 10
MAX_SIZE = 10

class Shape(object):
    def __init__(self):
        pass

    def resolve(self, storage, index):
        raise NotImplementedError("abstract base class")

    def num_storage_vars(self):
        return 0

    def depth(self):
        return 1

INEFFICIENT = Shape()
SEEN_ONCE = Shape()

class WrapShape(Shape):
    _immutable_fields_ = ["w_obj"]
    def __init__(self, w_obj):
        Shape.__init__(self)
        self.w_obj = w_obj

    def resolve(self, storage, index):
        return self.w_obj

    def replace(self, i, shape):
        assert 0, "cannot happen"

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.w_obj)

class InStorageShape(Shape):

    def __init__(self):
        Shape.__init__(self)

    @staticmethod
    def build():
        return InStorageShape._singleton

    def resolve(self, storage, index):
        return storage[index]

    def num_storage_vars(self):
        return 1

    def replace(self, i, shape):
        assert i == 0
        return shape

    def __repr__(self):
        return self.__class__.__name__ + "()"

InStorageShape._singleton = InStorageShape()

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
    _immutable_fields_ = ["signature", "children[*]"]
    _cache = objectmodel.r_dict(shape_eq, shape_hash)
    _transitions = None

    def __init__(self, signature, children):
        Shape.__init__(self)
        self.signature = signature
        self.children = children
        children = debug.make_sure_not_resized(children)
        _num_storage_vars = 0
        for child in self.children:
            _num_storage_vars += child.num_storage_vars()
        self._num_storage_vars = _num_storage_vars

    @staticmethod
    def build(signature, children):
        key = signature, children
        res = SharingShape._cache.get(key, None)
        if res is None:
            SharingShape._cache[key] = res = SharingShape(signature, children)
        return res

    def resolve(self, storage, index):
        storage = storage[index:index + self.num_storage_vars()]
        return ShapedCallable(self, storage)

    def resolve_at(self, i, storage):
        index = 0
        for j in range(i):
            index += self.children[j].num_storage_vars()
        return self.children[i].resolve(storage, index)

    @staticmethod
    def build_potentially_wrap(signature, children):
        unwrapped = [None] * len(children)
        for i in range(len(children)):
            child = children[i]
            if not isinstance(child, WrapShape):
                return SharingShape.build(signature, children)
            unwrapped[i] = child.w_obj
        return WrapShape(term.Callable.build(signature.name, unwrapped,
                                        signature=signature))

    def num_storage_vars(self):
        return self._num_storage_vars

    def replace(self, i, shape):
        for j in range(len(self.children)):
            child = self.children[j]
            num = child.num_storage_vars()
            if i < num:
                child = child.replace(i, shape)
                break
            else:
                i -= num
        else:
            assert 0, "cannot happen"
        children = self.children[:j] + [child] + self.children[j + 1:]
        return SharingShape.build(self.signature, children)

    def depth(self):
        depth = 0
        for child in self.children:
            depth = max(depth, child.depth())
        return depth + 1

    def get_transition(self, i, shape):
        if self._transitions is None:
            self._transitions = {}
        key = (i, shape)
        newshape = self._transitions.get(key, None)
        # XXX tune heuristics
        if newshape is None:
            self._transitions[key] = SEEN_ONCE
            return None
        elif newshape is SEEN_ONCE:
            newshape = self.replace(i, shape)
            if (newshape.depth() < MAX_DEPTH and
                    newshape.num_storage_vars() < MAX_SIZE):
                self._transitions[key] = newshape
            else:
                self._transitions[key] = INEFFICIENT
                return None
        elif newshape is INEFFICIENT:
            return None
        return newshape

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


# _____________________________________________________________________

class ShapedCallable(term.MutableCallable):
    TYPE_STANDARD_ORDER = term.Term.TYPE_STANDARD_ORDER

    def __init__(self, shape, storage):
        assert isinstance(shape, SharingShape)
        self.shape = shape
        storage = debug.make_sure_not_resized(storage)
        self.storage = storage
        assert shape.num_storage_vars() == len(storage)

    # _____________________________________________________________________
    # callable interface

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
        return term.Callable.basic_unify(self, other, heap, occurs_check)

    @jit.unroll_safe
    def copy_and_basic_unify(self, other, heap, env):
        if (isinstance(other, ShapedCallable) and
                self.shape is other.shape):
            for i in range(len(self.storage)):
                self.storage[i].unify_and_standardize_apart(other.storage[i], heap, env)
            return
        return term.Callable.copy_and_basic_unify(self, other, heap, env)

    def copy(self, heap, memo):
        from prolog.interpreter.term import _term_copy
        return self._copy_term(_term_copy, heap, memo)

    def copy_standardize_apart(self, heap, env):
        storage = [None] * len(self.storage)
        result = ShapedCallable(self.shape, storage)
        newinstance = False
        needmutable = False
        i = 0
        for i in range(len(self.storage)):
            arg = self.storage[i]
            cloned = arg.copy_standardize_apart_as_child_of(heap, env, result, i)
            newinstance = newinstance | (isinstance(arg, term.NumberedVar) or cloned is not arg)
            storage[i] = cloned
        if newinstance:
            return result
        else:
            return self

    def enumerate_vars(self, memo):
        from prolog.interpreter.term import _term_enumerate_vars
        return self._copy_term(_term_enumerate_vars, None, memo)

    @objectmodel.specialize.arg(1)
    @jit.unroll_safe
    def _copy_term(self, copy_individual, heap, *extraargs):
        args = [None] * len(self.storage)
        newinstance = False
        i = 0
        while i < len(self.storage):
            arg = self.storage[i]
            cloned = copy_individual(arg, i, heap, *extraargs)
            newinstance = newinstance | (cloned is not arg)
            args[i] = cloned
            i += 1
        if newinstance:
            # XXX what about the variable shunting in Callable.build?
            return ShapedCallable(self.shape, args)
        else:
            return self

    def contains_var(self, var, heap):
        for arg in self.storage:
            if arg.contains_var(var, heap):
                return True
        return False

    # _____________________________________________________________________
    # shape-specific interface

    def _replace_child(self, i, obj, new_shape):
        assert isinstance(obj, ShapedCallable)
        self.storage = self.storage[:i] + obj.storage + self.storage[i + 1:]
        assert len(self.storage) == new_shape.num_storage_vars()
        self.shape = new_shape

    def replace_child(self, i, obj):
        if isinstance(obj, ShapedCallable):
            new_shape = self.shape.get_transition(i, obj.shape)
            if new_shape is not None:
                self._replace_child(i, obj, new_shape)
                return True
        return False

    @staticmethod
    def build(shape, children):
        result = ShapedCallable(shape, children)
        i = 0
        while i < len(result.storage):
            child = result.storage[i]
            if not result.replace_child(i, child):
                i += 1
        assert result.shape.num_storage_vars() == len(result.storage)
        return result



# _____________________________________________________________________

def make_standardizer(w_obj):
    memo = []
    shape = term_with_numbered_vars_to_shape(w_obj, memo)
    return Standardizer(shape, memo)

def term_with_numbered_vars_to_shape(w_obj, memo):
    from prolog.interpreter import term
    if isinstance(w_obj, term.NumberedVar):
        memo.append(w_obj.num)
        return InStorageShape.build()
    elif isinstance(w_obj, term.Callable):
        argshapes = [term_with_numbered_vars_to_shape(w_arg, memo)
                        for w_arg in w_obj.arguments()]
        return SharingShape.build_potentially_wrap(w_obj.signature(), argshapes)
    return WrapShape(w_obj)

class Standardizer(object):
    def __init__(self, shape, memo):
        self.shape = shape
        self.memo = memo

    def make_shaped_callable(self, env, heap):
        storage = [None] * len(self.memo)
        for i in range(len(self.memo)):
            index = self.memo[i]
            if index < 0:
                # XXX
                obj = heap.newvar()
            else:
                obj = env[index]
                if obj is None:
                    obj = env[index] = heap.newvar()
            storage[i] = obj
        return self.shape.resolve(storage, 0)

# _____________________________________________________________________

