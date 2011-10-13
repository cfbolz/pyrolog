from pypy.rlib import jit, objectmodel, debug, unroll
from prolog.interpreter import term
from prolog.interpreter.graphviz import _dot, view
# a Callable implementation that tries to save memory

# XXX tune this
MAX_DEPTH = 6
MAX_SIZE = 6
SHAPED_CALLABLE_SIZE = 6

class Shape(object):
    _attrs_ = []
    def __init__(self):
        pass

    def resolve(self, shaped_callable, index):
        raise NotImplementedError("abstract base class")

    def num_storage_vars(self):
        return 0

    def depth(self):
        return 1

    def get_path(self, index):
        raise NotImplementedError("abstract base class")

    def str(self):
        return ""

    def __repr__(self):
        return self.str()

    _dot = _dot

INEFFICIENT = Shape()
SEEN_ONCE = Shape()

class WrapShape(Shape):
    _immutable_fields_ = ["w_obj"]
    def __init__(self, w_obj):
        Shape.__init__(self)
        self.w_obj = w_obj

    def resolve(self, shaped_callable, index):
        return self.w_obj

    def replace(self, i, shape):
        assert 0, "cannot happen"

    def str(self):
        return "WrapShape(%s)" % (self.w_obj, )

class InStorageShape(Shape):

    def __init__(self):
        Shape.__init__(self)

    @staticmethod
    def build():
        return InStorageShape._singleton

    def resolve(self, shaped_callable, index):
        return shaped_callable.get_storage(index)

    def num_storage_vars(self):
        return 1

    def replace(self, i, shape):
        assert i == 0
        return shape

    def str(self):
        return "InStorageShape()"

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
    _immutable_fields_ = ["signature", "children[*]", "_num_storage_vars", "paths[*]"]
    _cache = objectmodel.r_dict(shape_eq, shape_hash)
    _transitions = None

    def __init__(self, signature, children):
        Shape.__init__(self)
        self.signature = signature
        self.children = children
        children = debug.make_sure_not_resized(children)
        _num_storage_vars = 0
        paths = []
        for i in range(len(children)):
            child = children[i]
            _num_storage_vars += child.num_storage_vars()
            if isinstance(child, InStorageShape):
                paths.append(term.VarInTermPath([i]))
            elif isinstance(child, SharingShape):
                for subpath in child.paths:
                    if subpath is not None:
                        paths.append(term.VarInTermPath([i] + subpath.path))
        self._num_storage_vars = _num_storage_vars
        assert len(paths) == _num_storage_vars
        self.paths = paths[:]

    @staticmethod
    def build(signature, children):
        key = signature, children
        res = SharingShape._cache.get(key, None)
        if res is None:
            SharingShape._cache[key] = res = SharingShape(signature, children)
        return res

    @staticmethod
    @jit.elidable
    def build_flat(signature, numargs):
        children = [InStorageShape.build()] * numargs
        return SharingShape.build(signature, children)


    @jit.unroll_safe
    def resolve(self, shaped_callable, index):
        storage = [shaped_callable.get_storage(i)
                      for i in range(index, index + self.num_storage_vars())]
        # XXX fix up vars in term?
        # XXX use build here?
        return shaped_callable.new(self, storage)

    @jit.unroll_safe
    def _find_storage_index(self, argument_index):
        storage_index = 0
        for j in range(argument_index):
            storage_index += self.children[j].num_storage_vars()
        return storage_index

    def resolve_at(self, argument_index, shaped_callable):
        return self.children[argument_index].resolve(shaped_callable,
                self._find_storage_index(argument_index))

    @jit.unroll_safe
    def resolve_indicator(self, indicator, shaped_callable):
        storage_index = 0
        for i in indicator.path:
            storage_index += self._find_storage_index(i)
            self = self.children[i]
        return self.resolve(shaped_callable, storage_index)

    def get_path(self, index):
        return self.paths[index]

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

    @jit.elidable
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

    @jit.elidable_promote('all')
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
            if (newshape.depth() <= MAX_DEPTH and
                    newshape.num_storage_vars() <= MAX_SIZE):
                self._transitions[key] = newshape
            else:
                self._transitions[key] = INEFFICIENT
                return None
        elif newshape is INEFFICIENT:
            return None
        assert isinstance(newshape, SharingShape)
        return newshape

    def str(self):
        return "SharingShape(%s, [%s])" % (self.signature.string(), ", ".join([child.str() for child in self.children]))

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

class ShapedCallableBase(term.Callable):
    _attrs_ = []

    def get_shape(self):
        raise NotImplementedError("abstract base class")

    def get_storage(self, i):
        raise NotImplementedError("abstract base class")

    def set_storage(self, i, val):
        raise NotImplementedError("abstract base class")

    def size_storage(self):
        raise NotImplementedError("abstract base class")

    def new(self, shape, storage):
        raise NotImplementedError("abstract base class")

    @jit.unroll_safe
    def get_mode(self):
        from pypy.rlib.rarithmetic import intmask
        mode = 0x345678
        for i in range(self.size_storage()):
            child = self.get_storage(i)
            y = 0
            if isinstance(child, term.VarInTerm):
                parent = child.parent
                shape = parent.get_shape()
                indicator = child.indicator
                if isinstance(indicator, term.VarInTermIndex):
                    y = objectmodel.compute_identity_hash(shape)
                else:
                    y = 0
            mode = intmask((1000003 * mode) ^ y)
        return mode

UNROLL_N = unroll.unrolling_iterable(range(SHAPED_CALLABLE_SIZE))
UNROLL_R = unroll.unrolling_iterable(range(SHAPED_CALLABLE_SIZE)[::-1])

class ShapedCallableMixin:
    TYPE_STANDARD_ORDER = term.Term.TYPE_STANDARD_ORDER
    _mixin_ = True

    rest_storage = None

    def __init__(self, shape, storage):
        assert isinstance(shape, SharingShape)
        self.shape = shape
        assert shape.num_storage_vars() == len(storage)
        self.set_full_storage(storage)

    def get_shape(self):
        return jit.promote(self.shape)

    def set_shape(self, shape):
        self.shape = shape

    def get_storage(self, i):
        for n in UNROLL_N:
            if i == n:
                return getattr(self, "a%s" % n)
        return self.rest_storage[i - SHAPED_CALLABLE_SIZE]

    def set_storage(self, i, val):
        assert val is not None
        for n in UNROLL_N:
            if i == n:
                setattr(self, "a%s" % n, val)
                break
        else:
            self.rest_storage[i - SHAPED_CALLABLE_SIZE] = val

    def size_storage(self):
        return self.get_shape().num_storage_vars()


    def get_full_storage(self):
        # this is very much over the top, but it was fun to do
        size = self.size_storage()
        result = [None] * min(size, SHAPED_CALLABLE_SIZE)
        if size == 0:
            return result
        for n in UNROLL_N:
            if size == n + 1:
                break
        else:
            result = result + self.rest_storage
            n = SHAPED_CALLABLE_SIZE - 1
        for i in UNROLL_R:
            if n == i:
                result[i] = getattr(self, "a%s" % i)
                n = i - 1
        return result

    def set_full_storage(self, storage):
        # this is very much over the top, but it was fun to do
        size = self.size_storage()
        self.rest_storage = None
        if size == 0:
            return
        # the trick: "promote" size
        for n in UNROLL_N:
            if size == n + 1:
                break
        else:
            self.rest_storage = storage[SHAPED_CALLABLE_SIZE:]
            n = SHAPED_CALLABLE_SIZE - 1
        for i in UNROLL_R:
            if n == i:
                setattr(self, "a%s" % i, storage[i])
                n = i - 1

    # _____________________________________________________________________
    # callable interface

    def signature(self):
        return self.get_shape().signature

    def argument_at(self, i):
        return self.get_shape().resolve_at(i, self)

    def argument_count(self):
        return self.signature().numargs

    @objectmodel.specialize.arg(3)
    @jit.unroll_safe
    def basic_unify(self, other, heap, occurs_check=False):
        if (isinstance(other, ShapedCallableBase) and
                self.get_shape() is other.get_shape()):
            for i in range(self.size_storage()):
                self.get_storage(i).unify(other.get_storage(i), heap, occurs_check)
            return
        return term.Callable.basic_unify(self, other, heap, occurs_check)

    @jit.unroll_safe
    def copy_and_basic_unify(self, other, heap, env):
        if (isinstance(other, ShapedCallableBase) and
                self.get_shape() is other.get_shape()):
            for i in range(self.size_storage()):
                self.get_storage(i).unify_and_standardize_apart(
                        other.get_storage(i), heap, env)
            return
        return term.Callable.copy_and_basic_unify(self, other, heap, env)

    def copy(self, heap, memo):
        from prolog.interpreter.term import _term_copy
        return self._copy_term(_term_copy, heap, memo)

    @jit.unroll_safe
    def copy_standardize_apart(self, heap, env):
        storage = [None] * self.size_storage()
        result = ShapedCallableMutable(self.get_shape(), storage)
        newinstance = False
        needmutable = False
        i = 0
        for i in range(self.size_storage()):
            arg = self.get_storage(i)
            cloned = arg.copy_standardize_apart_as_child_of(heap, env, result, i)
            newinstance = newinstance | (isinstance(arg, term.NumberedVar) or cloned is not arg)
            needmutable = needmutable | isinstance(cloned, term.VarInTerm)
            result.set_storage(i, cloned)
        if newinstance:
            if not needmutable:
                result = result._make_immutable()
            return result.compress()
        else:
            return self

    def enumerate_vars(self, memo):
        from prolog.interpreter.term import _term_enumerate_vars
        return self._copy_term(_term_enumerate_vars, None, memo)

    @objectmodel.specialize.arg(1)
    @jit.unroll_safe
    def _copy_term(self, copy_individual, heap, *extraargs):
        args = [None] * self.size_storage()
        newinstance = False
        i = 0
        while i < self.size_storage():
            arg = self.get_storage(i)
            cloned = copy_individual(arg, i, heap, *extraargs)
            newinstance = newinstance | (cloned is not arg)
            args[i] = cloned
            i += 1
        if newinstance:
            # XXX what about the variable shunting in Callable.build?
            return self.new(self.get_shape(), args)
        else:
            return self

    def contains_var(self, var, heap):
        for i in range(self.size_storage()):
            arg = self.get_storage(i)
            if arg.contains_var(var, heap):
                return True
        return False

    # _____________________________________________________________________
    # shape-specific interface

    @jit.unroll_safe
    def _replace_child(self, index, obj, new_shape):
        assert isinstance(obj, ShapedCallableBase)
        newsize = obj.size_storage() + self.size_storage() - 1
        assert newsize == new_shape.num_storage_vars()
        offset = obj.size_storage() - 1
        old_shape = self.shape
        self.set_shape(new_shape)
        if offset < 0:
            for i in range(index + 1, self.size_storage()):
                self.move_child(i, i + offset)
        else:
            if offset > 0:
                for i in range(old_shape.num_storage_vars() - 1, index, -1):
                    self.move_child(i, i + offset)
            for i in range(obj.size_storage()):
                child = obj.get_storage(i)
                # XXX whew, subtle logic here
                if isinstance(child, term.VarInTerm):
                    deref = child.getbinding()
                    if deref is None:
                        self = self._make_mutable()
                        child.parent = self
                        child.indicator = term.VarInTermIndex.build(i + index)
                    else:
                        child = deref
                self.set_storage(i + index, child)
        return self

    def move_child(self, index, newindex):
        child = self.get_storage(index)
        if isinstance(child, term.VarInTerm):
            child = child.move(self, index, newindex)
        self.set_storage(newindex, child)

    def replace_child(self, index, obj):
        if isinstance(obj, ShapedCallableBase):
            new_shape = self.get_shape().get_transition(index, obj.get_shape())
            if new_shape is not None:
                assert new_shape.num_storage_vars() <= SHAPED_CALLABLE_SIZE
                return self._replace_child(index, obj, new_shape)
        return None

    @staticmethod
    def build(shape, storage):
        if isinstance(shape, WrapShape):
            assert not storage
            return shape.w_obj
        result = ShapedCallable(shape, storage)
        return result.compress()

    @jit.unroll_safe
    def compress(self):
        i = 0
        while i < self.size_storage():
            child = self.get_storage(i)
            newresult = self.replace_child(i, child)
            if not newresult:
                i += 1
            else:
                self = newresult
        assert self.get_shape().num_storage_vars() == self.size_storage()
        return self

    _dot = _dot

for i in range(SHAPED_CALLABLE_SIZE):
    setattr(ShapedCallableMixin, "a%s" % i, None)

class ShapedCallableMutable(ShapedCallableMixin, ShapedCallableBase):
    def _make_immutable(self):
        return ShapedCallable(self.get_shape(), self.get_full_storage())

    def _make_mutable(self):
        return self

    def new(self, shape, storage):
        return ShapedCallableMutable(shape, storage)


class ShapedCallable(ShapedCallableMixin, ShapedCallableBase):
    _immutable_fields_ = ["shape", "rest_storage[*]"] + ["a%s" % i for i in range(SHAPED_CALLABLE_SIZE)]

    def _make_mutable(self):
        return ShapedCallableMutable(self.get_shape(), self.get_full_storage())

    def new(self, shape, storage):
        return ShapedCallable(shape, storage)


# _____________________________________________________________________

def make_standardizer(w_obj):
    memo = []
    shape = term_with_numbered_vars_to_shape(w_obj, memo)
    return Standardizer(shape, memo[:])

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
    _immutable_fields_ = ["shape", "memo[*]"]
    def __init__(self, shape, memo):
        self.shape = shape
        self.memo = memo

    @jit.unroll_safe
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
        return ShapedCallable.build(self.shape, storage)

# _____________________________________________________________________

