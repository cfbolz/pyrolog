from prolog.interpreter import shape, term, signature

def test_wrap():
    s = shape.WrapShape(term.Callable.build("a", [term.Number(1)]))
    w_obj = s.resolve([1, 2, 3])
    assert w_obj.name() == "a"
    assert w_obj.argument_at(0).num == 1

    assert s.resolve_at(0, None).num == 1

def test_instorage():
    s = shape.InStorageShape(0)
    assert s.resolve([1, 2, 3]) == 1

    w_obj = s.resolve_at(0, [term.Callable.build("a", [term.Number(1)])])
    assert w_obj.num == 1

def test_sharing():
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
