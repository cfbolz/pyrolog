from prolog.interpreter import shape, term, signature
from prolog.interpreter.continuation import view

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
    w_obj = s.resolve([1, 2, 3], 0)
    assert w_obj.name() == "a"
    assert w_obj.argument_at(0).num == 1


def test_instorage_resolve():
    s = shape.InStorageShape()
    assert s.resolve([1, 2, 3], 0) == 1
    assert s.resolve([1, 2, 3], 1) == 2
    assert s.resolve([1, 2, 3], 2) == 3


def test_sharing_resolve():
    sig = signature.Signature.getsignature("f", 2)
    s = shape.SharingShape(sig, [
        shape.WrapShape(term.Callable.build("a")),
        shape.InStorageShape()
    ])
    assert s.resolve_at(0, [1, 2]).name() == "a"
    assert s.resolve_at(1, [1, 2]) == 1

    w_obj = s.resolve([1, 2], 0)
    assert isinstance(w_obj, shape.ShapedCallable)
    w_obj.argument_at(0).name() == "a"
    w_obj.argument_at(1) == 2

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
    assert w_obj.storage == [4, 5]


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
    assert w_obj.storage == [4, 4, 5, 7]
    w_obj = std.make_shaped_callable([4, None], FakeHeap())
    assert w_obj.storage == [4, 4, 7, 7]

    class FakeHeap(object):
        def newvar(self):
            return object()
    w_obj = std.make_shaped_callable([None, None], FakeHeap())
    assert w_obj.storage[0] is w_obj.storage[1]

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
    build = shape.SharingShape.build
    X = shape.InStorageShape.build()
    s1 = build(sig, [X, X])
    a = term.Callable.build("a")
    b = term.Callable.build("b")
    nil = term.Callable.build("[]")
    c1 = shape.ShapedCallable(s1, [a, None])
    c2 = shape.ShapedCallable(s1, [b, nil])
    newshape = s1.replace(1, s1)
    c1._replace_child(1, c2, newshape)
    assert c1.storage == [a, b, nil]

    c1 = shape.ShapedCallable(s1, [None, a])
    c2 = shape.ShapedCallable(s1, [b, nil])
    newshape = s1.replace(0, s1)
    c1._replace_child(0, c2, newshape)
    assert c1.storage == [b, nil, a]

def test_depth():
    sig = signature.Signature.getsignature(".", 2)
    b = shape.SharingShape.build
    X = shape.InStorageShape.build()
    s1 = b(sig, [X, X])
    assert s1.depth() == 2
    s = s1
    for i in range(10):
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
    for i in range(8):
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
    assert c3.storage == [4, 3, 2, nil]
    c4 = shape.ShapedCallable.build(s1, [4, c2])
    assert c4.storage == [4, 3, 2]

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


