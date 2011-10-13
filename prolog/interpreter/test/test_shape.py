import py
from prolog.interpreter import shape, term, signature
from prolog.interpreter.continuation import view

class FakeShapedCallable(object):
    def __init__(self, l):
        self.storage = l

    def get_storage(self, i):
        return self.storage[i]

def test_instorage_build():
    assert shape.InStorageShape.build() is shape.InStorageShape.build()

def test_sharing_build():
    sig = signature.Signature.getsignature("f", 2)
    s1 = shape.SharingShape.build(sig, [shape.InStorageShape.build(),
                                        shape.InStorageShape.build()])
    s2 = shape.SharingShape.build(sig, [shape.InStorageShape.build(),
                                        shape.InStorageShape.build()])
    assert s1 is s2
    sig = signature.Signature.getsignature("g", 2)
    s3 = shape.SharingShape.build(sig, [shape.InStorageShape.build(),
                                        shape.InStorageShape.build()])
    assert s3 is not s2

def test_wrapshape_resolve():
    s = shape.WrapShape(term.Callable.build("a", [term.Number(1)]))
    w_obj = s.resolve(FakeShapedCallable([1, 2, 3]), 0)
    assert w_obj.name() == "a"
    assert w_obj.argument_at(0).num == 1


def test_instorage_resolve():
    s = shape.InStorageShape()
    assert s.resolve(FakeShapedCallable([1, 2, 3]), 0) == 1
    assert s.resolve(FakeShapedCallable([1, 2, 3]), 1) == 2
    assert s.resolve(FakeShapedCallable([1, 2, 3]), 2) == 3


def test_sharing_resolve():
    sig = signature.Signature.getsignature("f", 2)
    s = shape.SharingShape(sig, [
        shape.WrapShape(term.Callable.build("a")),
        shape.InStorageShape()
    ])
    assert s.resolve_at(0, FakeShapedCallable([1, 2])).name() == "a"
    assert s.resolve_at(1, FakeShapedCallable([1, 2])) == 1

    w_obj = s.resolve(shape.ShapedCallable(s, [2]), 0)
    assert isinstance(w_obj, shape.ShapedCallable)
    w_obj.argument_at(0).name() == "a"
    w_obj.argument_at(1) == 2


def test_get_path():
    sig = signature.Signature.getsignature(".", 2)
    build = shape.SharingShape
    X = shape.InStorageShape.build()
    s1 = build(sig, [X, X])
    s2 = build(sig, [X, s1])
    p = s2.get_path(0).path
    assert p == [0]
    p = s2.get_path(1).path
    assert p == [1, 0]
    p = s2.get_path(2).path
    assert p == [1, 1]


def test_build_potentially_wrap():
    sig = signature.Signature.getsignature("f", 2)
    sh = shape.SharingShape.build_potentially_wrap(
        sig, [shape.WrapShape(term.Number(1)),
              shape.WrapShape(term.Callable.build("a"))])
    assert isinstance(sh, shape.WrapShape)

def test_make_standardizer():
    w_obj = term.Callable.build("f", [term.Callable.build("a"),
                                      term.Number(12),
                                      term.NumberedVar(0),
                                      term.NumberedVar(1)])
    std = shape.make_standardizer(w_obj)
    s = std.shape
    assert isinstance(s, shape.SharingShape)
    assert s.children[0].w_obj.signature().name == "a"
    assert s.children[1].w_obj.num == 12
    assert isinstance(s.children[2], shape.InStorageShape)
    assert isinstance(s.children[3], shape.InStorageShape)
    w_obj = std.make_shaped_callable([4, 5], None)
    assert w_obj.get_full_storage() == [4, 5]


    w_obj = term.Callable.build("f", [term.Callable.build("a"),
                                      term.Number(12)])
    std = shape.make_standardizer(w_obj)
    s = std.shape
    assert isinstance(s, shape.WrapShape)
    assert s.w_obj.signature().name == "f"
    w_obj = std.make_shaped_callable([], None)
    assert w_obj is s.w_obj

    w_obj = term.Callable.build("f", [term.NumberedVar(0),
                                      term.NumberedVar(0),
                                      term.NumberedVar(1),
                                      term.NumberedVar(-1)])
    std = shape.make_standardizer(w_obj)
    s = std.shape
    assert s.signature.name == "f"
    assert isinstance(s.children[0], shape.InStorageShape)
    assert isinstance(s.children[1], shape.InStorageShape)
    assert isinstance(s.children[2], shape.InStorageShape)
    assert isinstance(s.children[3], shape.InStorageShape)
    assert std.memo == [0, 0, 1, -1]
    class FakeHeap(object):
        def newvar(self):
            return 7
    w_obj = std.make_shaped_callable([4, 5], FakeHeap())
    assert w_obj.get_full_storage() == [4, 4, 5, 7]
    w_obj = std.make_shaped_callable([4, None], FakeHeap())
    assert w_obj.get_full_storage() == [4, 4, 7, 7]

    class FakeHeap(object):
        def newvar(self):
            return object()
    w_obj = std.make_shaped_callable([None, None], FakeHeap())
    assert w_obj.get_storage(0) is w_obj.get_storage(1)

def test_replace():
    sig = signature.Signature.getsignature(".", 2)
    b = shape.SharingShape.build
    X = shape.InStorageShape.build()
    s1 = b(sig, [X, X])
    s2 = s1.replace(1, s1)
    s2b = b(sig, [X, s1])
    assert s2 is s2b

    s3 = s2.replace(2, s1)
    s3b = b(sig, [X, s2])
    assert s3 is s3b

    nil = shape.WrapShape(term.Atom.build("[]"))
    s4 = s3.replace(3, nil)
    s4b = b(sig, [X, b(sig, [X, b(sig, [X, nil])])])
    assert s4b is s4

def test_shaped_callable_replace_child():
    sig = signature.Signature.getsignature(".", 2)
    build = shape.SharingShape
    X = shape.InStorageShape.build()
    s1 = build(sig, [X, X])
    a = term.Callable.build("a")
    b = term.Callable.build("b")
    nil = term.Callable.build("[]")
    c1 = shape.ShapedCallable(s1, [a, None])
    c2 = shape.ShapedCallable(s1, [b, nil])
    newshape = s1.replace(1, s1)
    c1._replace_child(1, c2, newshape)
    assert c1.get_full_storage() == [a, b, nil]

    c1 = shape.ShapedCallable(s1, [None, a])
    c2 = shape.ShapedCallable(s1, [b, nil])
    newshape = s1.replace(0, s1)
    c1._replace_child(0, c2, newshape)
    assert c1.get_full_storage() == [b, nil, a]

def test_replace_child_fixup_varinterm_at_end():
    from prolog.interpreter.heap import Heap
    h = Heap()
    sig = signature.Signature.getsignature(".", 3)
    build = shape.SharingShape
    X = shape.InStorageShape.build()
    s1 = build(sig, [X, X, X])
    a = term.Callable.build("a")
    b = term.Callable.build("b")
    c = term.Callable.build("c")
    nil = term.Callable.build("[]")
    c1 = shape.ShapedCallableMutable(s1, [a, None, None])

    c2 = shape.ShapedCallableMutable(s1, [b, c, c])
    var1 = h.newvar_in_term(c1, 2)
    c1.set_storage(2, var1)

    s1.get_transition(1, s1)
    s2 = s1.get_transition(1, s1)
    c1._replace_child(1, c2, s2)
    assert c1.get_storage(4).parent is c1
    assert c1.get_storage(4).indicator.index == 4

    # if the variable is already bound, shunt it
    c1 = shape.ShapedCallableMutable(s1, [a, None, None])

    c2 = shape.ShapedCallableMutable(s1, [b, c, c])
    var1 = h.newvar_in_term(c1, 0)
    c1.set_storage(0, var1)
    c1.set_storage(2, var1)
    var1.setvalue(nil, h)
    assert c1.get_storage(0) is nil
    assert c1.get_storage(2) is var1

    s1.get_transition(1, s1)
    s2 = s1.get_transition(1, s1)
    c1._replace_child(1, c2, s2)
    assert c1.get_storage(4) is nil


def test_replace_child_fixup_varinterm_from_replacement():
    from prolog.interpreter.heap import Heap
    h = Heap()
    sig = signature.Signature.getsignature(".", 3)
    build = shape.SharingShape
    X = shape.InStorageShape.build()
    s1 = build(sig, [X, X, X])
    a = term.Callable.build("a")
    b = term.Callable.build("b")
    c = term.Callable.build("c")
    nil = term.Callable.build("[]")
    c1 = shape.ShapedCallableMutable(s1, [a, None, c])

    c2 = shape.ShapedCallableMutable(s1, [b, None, c])
    var2 = h.newvar_in_term(c2, 1)
    c2.set_storage(1, var2)

    s1.get_transition(1, s1)
    res = c1.replace_child(1, c2)
    assert res is c1
    assert c1.get_storage(2).parent is c1
    assert c1.get_storage(2).indicator.index == 2

    c1 = shape.ShapedCallable(s1, [a, None, c])
    c2 = shape.ShapedCallableMutable(s1, [b, None, c])
    var2 = h.newvar_in_term(c2, 1)
    c2.set_storage(1, var2)

    s1.get_transition(1, s1)
    res = c1.replace_child(1, c2)
    assert isinstance(res, shape.ShapedCallableMutable)
    assert res.get_storage(2).parent is res
    assert res.get_storage(2).indicator.index == 2

def test_depth():
    sig = signature.Signature.getsignature(".", 2)
    b = shape.SharingShape.build
    X = shape.InStorageShape.build()
    s1 = b(sig, [X, X])
    assert s1.depth() == 2
    s = s1
    for i in range(shape.MAX_DEPTH):
        s = s.replace(i, s1)
        assert s.depth() == 3 + i

def test_get_transition():
    sig = signature.Signature.getsignature(".", 2)
    b = shape.SharingShape
    X = shape.InStorageShape.build()
    s1 = b(sig, [X, X])

    s2 = s1.get_transition(1, s1)
    assert s2 is None
    s2 = s1.get_transition(1, s1)
    s2b = b(sig, [X, s1])
    assert str(s2) == str(s2b)

    s3 = s2.get_transition(2, s1)
    assert s3 is None
    s3 = s2.get_transition(2, s1)
    s3b = b(sig, [X, s2])
    assert str(s3) == str(s3b)

    nil = shape.WrapShape(term.Atom.build("[]"))
    s4 = s3.get_transition(3, nil)
    assert s4 is None
    s4 = s3.get_transition(3, nil)
    s4b = b(sig, [X, b(sig, [X, b(sig, [X, nil])])])
    assert str(s3) == str(s3b)

def test_get_transition_inefficient():
    sig = signature.Signature.getsignature(".", 2)
    b = shape.SharingShape
    X = shape.InStorageShape.build()
    s1 = b(sig, [X, X])
    s = s1
    for i in range(shape.SHAPED_CALLABLE_SIZE - 2):
        s.get_transition(i, s1)
        s = s.get_transition(i, s1)
    assert s is None
    sig10 = signature.Signature.getsignature(".", 10)
    s10 = b(sig10, [X] * 10)
    s10.get_transition(5, s1)
    assert s10.get_transition(5, s1) is None

def test_shaped_callable_build():
    sig = signature.Signature.getsignature(".", 2)
    b = shape.SharingShape
    X = shape.InStorageShape.build()
    s1 = b(sig, [X, X])
    s1.get_transition(1, s1)
    s2 = s1.get_transition(1, s1)
    s2.get_transition(2, s1)
    s3 = s2.get_transition(2, s1)
    nilsig = signature.Signature.getsignature("[]", 0)
    nilshape = b(nilsig, [])
    nil = shape.ShapedCallable(nilshape, [])
    c1 = shape.ShapedCallable(s1, [2, nil])
    c2 = shape.ShapedCallable(s1, [3, c1])
    c3 = shape.ShapedCallable.build(s1, [4, c2])
    assert c3.shape is s3
    assert c3.get_full_storage() == [4, 3, 2, nil]
    c4 = shape.ShapedCallable.build(s1, [4, c2])
    assert c4.get_full_storage() == [4, 3, 2]

def test_shaped_callable_unify():
    from prolog.interpreter import heap
    a = term.Callable.build("a")
    b = term.Callable.build("b")
    c = term.Callable.build("c")
    sig = term.Callable.build("f", [None, None, None, None]).signature()

    s = shape.SharingShape(sig, [
        shape.WrapShape(a),
        shape.InStorageShape(),
        shape.InStorageShape(),
        shape.InStorageShape(),
    ])
    h = heap.Heap()
    X = h.newvar()
    c1 = shape.ShapedCallable(s, [a, b, c])
    c1.argument_at = None
    c2 = shape.ShapedCallable(s, [X, b, c])
    c2.argument_at = None
    c1.unify(c2, h)
    assert X.binding is a

def test_functional_test():
    from prolog.interpreter.continuation import Engine
    from prolog.interpreter.test.tool import assert_true, get_engine
    e = get_engine("""
        append([], L, L).
        append([H|T], L, [H|R]) :- append(T, L, R).
        reverse([], L, L).
        reverse([H|T], L, O) :-
            reverse(T, [H | L], O).
    """)

    for i in range(10):
        env = assert_true("append([1, 2, 3, 4, 5], [2, 3, 4, 5, 6], X).", e)
    res = env['X']
    l = []
    while res.name() == ".":
        l.append(res.argument_at(0).num)
        res = res.argument_at(1)
    assert l == [1, 2, 3, 4, 5, 2, 3, 4, 5, 6]
    res = env['X']
    assert len(res.get_full_storage()) > shape.SHAPED_CALLABLE_SIZE - 2

    for i in range(10):
        env = assert_true("reverse([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [], X).", e)
    res = env['X']
    l = []
    while res.name() == ".":
        l.append(res.argument_at(0).num)
        res = res.argument_at(1)
    assert l == [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
    py.test.skip("the rest is failing atm")
    res = env['X']
    assert len(res.get_full_storage()) > shape.SHAPED_CALLABLE_SIZE - 2
