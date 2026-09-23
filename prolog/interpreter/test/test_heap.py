import pytest
from prolog.interpreter.heap import Heap
from prolog.interpreter.term import AttVar, BindingVar, Callable, Number, Atom, AttMap

def test_heap():
    h1 = Heap()
    v1 = h1.newvar()
    v2 = h1.newvar()
    h1.add_trail(v1)
    v1.binding = 1
    h2 = h1.branch()
    h2.add_trail(v1)
    v1.binding = 2
    h2.add_trail(v2)
    v2.binding = 3

    h3 = h2.revert_upto(h1)
    assert v1.binding == 1
    assert v2.binding is None
    assert h3 is h2

    h1 = Heap()
    h2 = h1.revert_upto(h1)
    assert h2 is h1

    h1 = Heap()
    h2 = h1.branch()
    h3 = h2.revert_upto(h1, discard_choicepoint=True)
    assert h3 is h1

def test_heap_dont_trail_new():
    h1 = Heap()
    v1 = h1.newvar()
    h1.add_trail(v1)
    v1.binding = 1
    h2 = h1.branch()
    v2 = h2.newvar()
    h2.add_trail(v1)
    v1.binding = 2
    h2.add_trail(v2)
    v2.binding = 3

    h3 = h2.revert_upto(h1)
    assert v1.binding == 1
    assert v2.binding == 3 # wasn't undone, because v2 dies
    assert h3 is h2

def test_heap_discard():
    h1 = Heap()
    h2 = h1.branch()
    h3 = h2.branch()
    h = h2.discard(h3)
    assert h3.prev is h1
    assert h3 is h

    h0 = Heap()
    v0 = h0.newvar()

    h1 = h0.branch()
    v1 = h1.newvar()

    h2 = h1.branch()
    v2 = h2.newvar()

    h2.add_trail(v0)
    v0.binding = 1
    h2.add_trail(v1)
    v1.binding = 2

    h3 = h2.branch()
    h3.add_trail(v2)
    v2.binding = 3

    h = h2.discard(h3)
    assert h3.prev is h1
    assert h3 is h

    assert h3.revert_upto(h0)
    assert v0.binding is None
    assert v1.binding is None
    assert v2.binding == 3 # not backtracked, because it goes away

@pytest.mark.parametrize('length', [2, 8])
def test_discard_preserves_path_compression_undo_order(length):
    root = Heap()
    variables = [root.newvar() for _ in range(length)]
    older = root.branch()
    for i in range(length - 1):
        variables[i].unify(variables[i + 1], older)
    # Also exercise multiple undo entries for one variable in the older frame.
    assert variables[0].dereference(older) is variables[-1]

    current = older.branch()
    value = Number(7)
    variables[-1].unify(value, current)
    for var in variables:
        assert var.dereference(current) is value
        assert var.binding is value

    assert older.discard(current) is current
    assert current.prev is root
    # A cut changes bookkeeping, not the live bindings.
    for var in variables:
        assert var.binding is value

    current.revert_upto(root)
    # Undo compression before undoing the original aliases: all variables
    # must become independent again, not remain linked to each other.
    for var in variables:
        assert var.binding is None


def test_trailing_after_discard_with_one_binding():
    root = Heap()
    variables = [root.newvar() for _ in range(4)]
    older = root.branch()
    variables[0].unify(Number(0), older)
    current = older.branch()
    older.discard(current)
    for i in range(1, len(variables)):
        variables[i].unify(Number(i), current)
    current.revert_upto(root)
    for var in variables:
        assert var.binding is None


def test_heap_discard_variable_shunting():
    h0 = Heap()
    v0 = h0.newvar()

    h1 = h0.branch()
    v1a = h1.newvar()
    v1b = h1.newvar()

    h2 = h1.branch()
    v2 = h1.newvar()

    h2.add_trail(v0)
    v0.binding = 1
    h2.add_trail(v1a)
    v1a.binding = 2

    h = h1.discard(h2)
    assert h2.prev is h0
    assert h2 is h
    assert h1.discarded
    assert h1.prev is h2

    h2.add_trail(v1b)
    v1b.binding = 3

    assert h2.revert_upto(h0)

    assert v0.binding is None
    assert v1a.binding == 2 # not backtracked, because it goes away
    assert v1b.binding == 3 # not backtracked, because it goes away

def test_new_attvar():
    h = Heap()
    v = h.new_attvar()
    assert isinstance(v, AttVar)
    assert v.created_after_choice_point is h

def test_add_trail_atts():
    hp = Heap()
    a = hp.new_attvar()
    assert a.created_after_choice_point is hp
    assert hp.trail_attrs is None
    ma = AttMap()
    ma.indexes = {"a": 0}
    a.value_list = [10]
    a.attmap = ma

    hp.add_trail_atts(a, "a")
    assert hp.trail_attrs is None
    hp2 = hp.branch()
    hp2.add_trail_atts(a, "a")
    assert hp2.trail_attrs == [(a, 0, 10)]
    a.add_attribute("a", 20)
    assert a.value_list == [20]
    hp2._revert()
    assert a.value_list == [10]

    hp3 = hp2.branch()
    hp3.add_trail_atts(a, "b")
    a.add_attribute("b", 30)
    assert a.value_list == [10, 30]
    assert a.attmap.indexes == {"a": 0, "b": 1}
    assert a.attmap is not ma
    hp3._revert()
    assert a.value_list == [10, None]

def test_heap_dont_trail_new_attvars():
    h1 = Heap()
    v1 = h1.new_attvar()
    h1.add_trail_atts(v1, "m")
    v1.add_attribute("m", 1)
    h2 = h1.branch()
    v2 = h2.new_attvar()
    h2.add_trail_atts(v1, "m")
    v1.add_attribute("m", 2)
    h2.add_trail_atts(v2, "m")
    v2.add_attribute("m", 3)

    h3 = h2.revert_upto(h1)
    t1 = v1.get_attribute("m")
    assert t1[0] == 1
    assert t1[1] == 0
    t2 = v2.get_attribute("m") # wasn't undone, because v2 dies
    assert t2[0] == 3
    assert t2[1] == 0
    assert h3 is h2
    
def test_discard_with_attvars():
    from prolog.builtin.attvars import impl_put_attr

    h0 = Heap()
    v0 = h0.new_attvar()

    h1 = h0.branch()
    v1 = h1.new_attvar()

    h2 = h1.branch()
    v2 = h2.new_attvar()

    impl_put_attr(None, h2, v0, "m", Number(1))
    impl_put_attr(None, h2, v1, "n", Number(2))

    h3 = h2.branch()
    impl_put_attr(None, h3, v2, "a", Number(3))
    impl_put_attr(None, h3, v0, "m", Number(4))

    h = h2.discard(h3)
    assert h3.prev is h1
    assert h3 is h
    # The cut keeps all live values, despite discarding v2's undo record.
    assert v0.get_attribute_value("m").num == 4
    assert v1.get_attribute_value("n").num == 2
    assert v2.get_attribute_value("a").num == 3

    h3.revert_upto(h0)
    assert v0.is_empty()
    assert v0.get_attribute_value("m") is None
    assert v1.is_empty()
    assert v1.get_attribute_value("n") is None
    # v2 was created in the discarded frame and dies on outer backtracking;
    # its attribute therefore does not need to be restored.
    assert v2.get_attribute_value("a").num == 3

def test_hookchain():
    hc = Heap()
    assert hc.hook is None
    hc.add_hook(1)
    hc.add_hook(2)
    hc.add_hook(3)
    assert hc.hook.attvar == 3
    assert hc.hook.next.attvar == 2
    assert hc.hook.next.next.attvar == 1
    assert hc.hook.next.next.next is None

def test_simple_hooks():
    hp = Heap()
    v = BindingVar()
    a = AttVar()
    v.unify(a, hp)
    assert hp.hook is None
    v.unify(Number(1), hp)
    assert hp.hook.attvar == a

    hp = Heap()
    v1 = BindingVar()
    v2 = BindingVar()
    a1 = AttVar()
    a2 = AttVar()
    v1.unify(a1, hp)
    assert hp.hook is None
    v2.unify(a2, hp)
    assert hp.hook is None
    v1.unify(v2, hp)
    assert hp.hook.attvar == a1

    hp = Heap()
    v1 = BindingVar()
    v2 = BindingVar()
    v3 = BindingVar()
    a1 = AttVar()
    a2 = AttVar()
    a3 = AttVar()
    v1.unify(a1, hp)
    v2.unify(a2, hp)
    v3.unify(a3, hp)

    v1.unify(v2, hp)
    v2.unify(v3, hp)
    assert hp.hook.attvar == a2
    assert hp.hook.next.attvar == a1
    assert hp.hook.next.next is None

    hp = Heap()
    v1 = BindingVar()
    v2 = BindingVar()
    a1 = AttVar()
    a2 = AttVar()
    v1.unify(a1, hp)
    v2.unify(a2, hp)
    assert hp.hook is None
    v1.unify(v2, hp)
    assert hp.hook.attvar == a1
    v1.unify(Number(1), hp)
    assert hp.hook.attvar == a2
    assert hp.hook.next.attvar == a1
    assert hp.hook.next.next is None

    hp = Heap()
    v1 = BindingVar()
    v2 = BindingVar()
    a1 = AttVar()
    a2 = AttVar()
    v1.unify(a1, hp)
    v2.unify(a2, hp)
    t1 = Callable.build("f", [v1, v2])
    t2 = Callable.build("f", [Atom("a"), Atom("b")])
    t1.unify(t2, hp)
    assert hp.hook.attvar == a2
    assert hp.hook.next.attvar == a1
    assert hp.hook.next.next is None

    hp = Heap()
    v = BindingVar()
    av = AttVar()
    v.unify(av, hp)
    assert hp.hook is None
    a = Callable.build("a")
    v.unify(a, hp)
    assert hp.hook.attvar == av
    v.unify(a, hp)
    assert hp.hook.attvar == av
    assert hp.hook.next is None

def test_hookchain_size():
    def size(heap):
        # for tests only
        if heap.hook is None:
            return 0
        current = heap.hook
        size = 0
        while current is not None:
            current = current.next
            size += 1
        return size
    h = Heap()
    assert size(h) == 0
    h.add_hook(1)
    assert size(h) == 1
    h.add_hook(2)
    assert size(h) == 2
    h.hook = None
    assert size(h) == 0
