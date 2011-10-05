from pypy.rlib import jit, objectmodel, debug
from prolog.interpreter import term
# a Callable implementation that tries to save memory

# XXX tune this
MAX_DEPTH = 10
MAX_SIZE = 10

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

    def get_path(self, i):
        assert 0, "cannot happen"

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.w_obj)

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

    def get_path(self, index):
        assert index == 0
        return []

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
    _immutable_fields_ = ["signature", "children[*]", "_num_storage_vars"]
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

    @jit.unroll_safe
    def resolve(self, shaped_callable, index):
        storage = [shaped_callable.get_storage(i)
                      for i in range(index, index + self.num_storage_vars())]
        # XXX fix up vars in term?
        # XXX use build here?
        return shaped_callable.new(self, storage)

    @jit.unroll_safe
    def resolve_at(self, i, shaped_callable):
        index = 0
        for j in range(i):
            index += self.children[j].num_storage_vars()
        return self.children[i].resolve(shaped_callable, index)

    def get_path(self, index):
        for j in range(len(self.children)):
            child = self.children[j]
            num = child.num_storage_vars()
            if index < num:
                return [j] + child.get_path(index)
            else:
                index -= num
        assert 0, "cannot happen"

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
            if (newshape.depth() < MAX_DEPTH and
                    newshape.num_storage_vars() < MAX_SIZE):
                self._transitions[key] = newshape
            else:
                self._transitions[key] = INEFFICIENT
                return None
        elif newshape is INEFFICIENT:
            return None
        assert isinstance(newshape, SharingShape)
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

class ShapedCallableMixin:
    TYPE_STANDARD_ORDER = term.Term.TYPE_STANDARD_ORDER
    _mixin_ = True

    def __init__(self, shape, storage):
        assert isinstance(shape, SharingShape)
        self.shape = shape
        storage = debug.make_sure_not_resized(storage)
        self.storage = storage
        assert shape.num_storage_vars() == len(storage)

    def get_shape(self):
        return jit.promote(self.shape)

    def get_storage(self, i):
        return self.storage[i]

    def set_storage(self, i, val):
        self.storage[i] = val

    def size_storage(self):
        return self.get_shape().num_storage_vars()

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
            arg = self.storage[i]
            cloned = arg.copy_standardize_apart_as_child_of(heap, env, result, i)
            newinstance = newinstance | (isinstance(arg, term.NumberedVar) or cloned is not arg)
            needmutable = needmutable | isinstance(cloned, term.VarInTerm)
            storage[i] = cloned
        if newinstance:
            if not needmutable:
                return result._make_immutable()
            return result
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
            arg = self.storage[i]
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
        for arg in self.storage:
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
        newstorage = [None] * newsize
        for i in range(index):
            newstorage[i] = self.storage[i]
        for i in range(obj.size_storage()):
            child = newstorage[i + index] = obj.get_storage(i)
            if isinstance(child, term.VarInTerm):
                indicator = child.indicator
                deref = child.getbinding()
                self = self._make_mutable()
                if deref is None:
                    child.parent = self
                    child.indicator = term.VarInTermIndex(i + index)
                else:
                    newstorage[i + index] = deref

        offset = obj.size_storage() - 1
        for i in range(index + 1, self.size_storage()):
            child = newstorage[i + offset] = self.storage[i]
            if isinstance(child, term.VarInTerm) and child.parent is self:
                assert isinstance(self, ShapedCallableMutable)
                indicator = child.indicator
                if (isinstance(indicator, term.VarInTermIndex) and
                        indicator.index == i):
                    child.indicator = term.VarInTermIndex(i + offset)
        self.storage = newstorage
        self.shape = new_shape
        return self

    def replace_child(self, index, obj):
        if isinstance(obj, ShapedCallableBase):
            new_shape = self.get_shape().get_transition(index, obj.get_shape())
            if new_shape is not None:
                return self._replace_child(index, obj, new_shape)
        return None

    @jit.unroll_safe
    def _fixup_var_in_term(self, obj, index):
        # XXX whew, subtle logic here
        newi = index
        for i in range(obj.size_storage()):
            old_child = obj.get_storage(i)
            assert self.get_storage(newi) is old_child
            if isinstance(old_child, term.VarInTerm):
                deref = old_child.getbinding()
                if deref is None:
                    self = self._make_mutable()
                    old_child.parent = self
                    old_child.indicator = term.VarInTermIndex(newi)
                else:
                    self.set_storage(newi, deref)
            newi += 1
        return self

    @staticmethod
    @jit.unroll_safe
    def build(shape, storage):
        if isinstance(shape, WrapShape):
            assert not storage
            return shape.w_obj
        result = ShapedCallable(shape, storage)
        i = 0
        while i < result.size_storage():
            child = result.get_storage(i)
            newresult = result.replace_child(i, child)
            if not newresult:
                i += 1
            else:
                result = newresult
        assert result.get_shape().num_storage_vars() == result.size_storage()
        return result

class ShapedCallableMutable(ShapedCallableMixin, ShapedCallableBase):
    def _make_immutable(self):
        return ShapedCallable(self.get_shape(), self.storage)

    def _make_mutable(self):
        return self

    def new(self, shape, storage):
        return ShapedCallableMutable(shape, storage)


class ShapedCallable(ShapedCallableMixin, ShapedCallableBase):
    _immutable_fields_ = ["shape", "storage[*]"]

    def _make_mutable(self):
        return ShapedCallableMutable(self.get_shape(), self.storage)

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

