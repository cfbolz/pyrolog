from prolog.interpreter import shape, term, signature

def test_instorage_build():
    assert shape.InStorageShape.build(1) is shape.InStorageShape.build(1)
    assert shape.InStorageShape.build(1).num == 1
    assert shape.InStorageShape.build(1) is not shape.InStorageShape.build(0)

def test_sharing_build():
    sig = signature.Signature.getsignature("f", 2)
    s1 = shape.SharingShape.build(sig, [shape.InStorageShape.build(1),
                                        shape.InStorageShape.build(2)])
    s2 = shape.SharingShape.build(sig, [shape.InStorageShape.build(1),
                                        shape.InStorageShape.build(2)])
    assert s1 is s2
    sig = signature.Signature.getsignature("g", 2)
    s3 = shape.SharingShape.build(sig, [shape.InStorageShape.build(1),
                                        shape.InStorageShape.build(2)])
    assert s3 is not s2
    s4 = shape.SharingShape.build(sig, [shape.InStorageShape.build(2),
                                        shape.InStorageShape.build(2)])
    assert s4 is not s3

def test_wrapshape_resolve():
    s = shape.WrapShape(term.Callable.build("a", [term.Number(1)]))
    w_obj = s.resolve([1, 2, 3])
    assert w_obj.name() == "a"
    assert w_obj.argument_at(0).num == 1

    assert s.resolve_at(0, None).num == 1

def test_instorage_resolve():
    s = shape.InStorageShape(0)
    assert s.resolve([1, 2, 3]) == 1

    w_obj = s.resolve_at(0, [term.Callable.build("a", [term.Number(1)])])
    assert w_obj.num == 1


def test_sharing_resolve():
    sig = signature.Signature.getsignature("f", 2)
    s = shape.SharingShape(sig, [
        shape.WrapShape(term.Callable.build("a")),
        shape.InStorageShape(1)
    ])
    assert s.resolve_at(0, [1, 2]).name() == "a"
    assert s.resolve_at(1, [1, 2]) == 2

    w_obj = s.resolve([1, 2])
    assert isinstance(w_obj, shape.ShapedCallable)
    w_obj.argument_at(0).name() == "a"
    w_obj.argument_at(1) == 2

def test_build_potentially_wrap():
    sig = signature.Signature.getsignature("f", 2)
    sh = shape.SharingShape.build_potentially_wrap(
        sig, [shape.WrapShape(term.Number(1)),
              shape.WrapShape(term.Callable.build("a"))])
    assert isinstance(sh, shape.WrapShape)

def test_term_with_numbered_vars_to_shape():
    w_obj = term.Callable.build("f", [term.Callable.build("a"),
                                      term.Number(12),
                                      term.NumberedVar(0),
                                      term.NumberedVar(1)])
    s = shape.term_with_numbered_vars_to_shape(w_obj)
    assert isinstance(s, shape.SharingShape)
    assert s.children[0].w_obj.signature().name == "a"
    assert s.children[1].w_obj.num == 12
    assert s.children[2].num == 0
    assert s.children[3].num == 1


    w_obj = term.Callable.build("f", [term.Callable.build("a"),
                                      term.Number(12)])
    s = shape.term_with_numbered_vars_to_shape(w_obj)
    assert isinstance(s, shape.WrapShape)
    assert s.w_obj.signature().name == "f"

def test_reshape():
    sig = signature.Signature.getsignature("f", 3)
    s = shape.SharingShape(sig, [
        shape.WrapShape(term.Callable.build("a")),
        shape.InStorageShape(0),
        shape.InStorageShape(1)
    ])
    rs = shape.Reshaper([5, 2], s)
    w_obj = rs.reshape(["a", "b", "c", "d", "e", "f"])
    assert w_obj.argument_at(1) == "f"
    assert w_obj.argument_at(2) == "c"

def test_compute_new_shape():
    s = shape.SharingShape("f", [
        shape.WrapShape(term.Callable.build("a")),
        shape.InStorageShape(5),
        shape.InStorageShape(2),
        shape.InStorageShape(2),
    ])
    memo = {}
    ns = s._compute_new_shape(memo)
    assert s.children[0] is ns.children[0]
    assert ns.children[1].num == 0
    assert ns.children[2].num == 1
    assert ns.children[3].num == 1
    assert memo == {5:0, 2:1}

def test_compute_new_shape_reuses():
    s = shape.WrapShape(term.Callable.build("a"))
    ns = s._compute_new_shape({})
    assert ns is s
    s = shape.InStorageShape(0)
    assert s._compute_new_shape({}) is s
    s = shape.SharingShape("f", [
        shape.WrapShape(term.Callable.build("a")),
        shape.InStorageShape(0),
        shape.InStorageShape(1),
        shape.InStorageShape(2),
    ])
    assert s._compute_new_shape({}) is s


def test_make_reshaper():
    s = shape.SharingShape("f", [
        shape.WrapShape(term.Callable.build("a")),
        shape.InStorageShape(5),
        shape.InStorageShape(2),
        shape.InStorageShape(2),
    ])
    rs = shape.make_reshaper(s)
    ns = rs.newshape
    assert s.children[0] is ns.children[0]
    assert ns.children[1].num == 0
    assert ns.children[2].num == 1
    assert ns.children[3].num == 1
    assert rs.storage_shaper == [5, 2]

def test_shaped_callable_unify():
    from prolog.interpreter import heap
    a = term.Callable.build("a")
    b = term.Callable.build("b")
    c = term.Callable.build("c")
    sig = term.Callable.build("f", [None, None, None, None]).signature()

    s = shape.SharingShape(sig, [
        shape.WrapShape(a),
        shape.InStorageShape(0),
        shape.InStorageShape(1),
        shape.InStorageShape(2),
    ])
    h = heap.Heap()
    X = h.newvar()
    c1 = shape.ShapedCallable(s, [a, b, c])
    c1.argument_at = None
    c2 = shape.ShapedCallable(s, [X, b, c])
    c2.argument_at = None
    c1.unify(c2, h)
    assert X.binding is a


def test_build_callable_shape():
    fsig = signature.Signature("f", 2)
    f0 = shape.SharingShape(fsig, [
        shape.InStorageShape.build(0),
        shape.InStorageShape.build(1),
    ])
    gsig = signature.Signature("g", 2)
    g0 = shape.SharingShape(gsig, [
        shape.InStorageShape.build(0),
        shape.InStorageShape.build(1),
    ])

    f1 = shape.SharingShape(fsig, [
        g0,
        shape.InStorageShape.build(2)
    ])
    f0.transitions = {(0, g0): f1}

    hsig = signature.Signature("h", 1)
    h0 = shape.SharingShape(hsig, [
        shape.InStorageShape.build(0),
    ])

    h1 = shape.SharingShape(hsig, [
        shape.InStorageShape.build(2),
    ])

    f2 = shape.SharingShape(fsig, [
        g0,
        h1
    ])

    f1.transitions = {(2, h0): f2}

    res = shape.build(f0, [
        shape.ShapedCallable(g0, [1, 2]),
        shape.ShapedCallable(h0, [3]),
    ])
    assert res.storage == [1, 2, 3]
    assert res.shape is f2

