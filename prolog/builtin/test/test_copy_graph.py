import pytest
from prolog.interpreter import term
from prolog.interpreter.continuation import Heap
from prolog.interpreter.memo import CopyMemo
from prolog.interpreter.test.tool import assert_true


@pytest.mark.parametrize('bound_edges', [False, True])
@pytest.mark.parametrize('ground', [False, True])
def test_copy_doubling_graph(monkeypatch, bound_edges, ground):
    heap = Heap()
    leaf = term.Callable.build('a') if ground else heap.newvar()
    root = leaf
    depth = 24
    for i in range(depth):
        obj = term.Callable.build('f', [root, root])
        if bound_edges:
            root = heap.newvar()
            root.setvalue(obj, heap)
        else:
            root = obj

    original_copy = term.Callable.copy
    visits = [0]

    def counted_copy(obj, heap, memo):
        visits[0] += 1
        assert visits[0] <= 2 * depth + 1, 'copy traversal expanded shared paths'
        return original_copy(obj, heap, memo)

    monkeypatch.setattr(term.Callable, 'copy', counted_copy)
    memo = CopyMemo()
    copied = root.copy(heap, memo).dereference(None)
    nodes = set()
    node = copied
    for i in range(depth):
        assert node not in nodes
        nodes.add(node)
        left = node.argument_at(0).dereference(None)
        right = node.argument_at(1).dereference(None)
        assert left is right
        node = left
    assert len(nodes) == depth
    if ground:
        assert node is leaf
        if not bound_edges:
            assert copied is root
    else:
        assert isinstance(node, term.Var)
        assert node.getbinding() is None
        assert node is not leaf
    # Acyclic graphs do not need placeholder variables.
    assert not memo.copying


def test_copy_cycle_preserves_back_edge():
    heap = Heap()
    back = heap.newvar()
    leaf = heap.newvar()
    original = term.Callable.build('f', [back, leaf, leaf])
    back.setvalue(original, heap)
    copied = original.copy(heap, CopyMemo()).dereference(None)
    assert copied is not original
    assert copied.argument_at(0).dereference(None) is copied
    a = copied.argument_at(1).dereference(None)
    assert a is copied.argument_at(2).dereference(None)
    assert isinstance(a, term.Var) and a.getbinding() is None
    assert a is not leaf


def test_copy_attributed_variable_self_reference():
    heap = Heap()
    original = heap.new_attvar()
    original.add_attribute('m', original)
    copied = original.copy(heap, CopyMemo())
    assert isinstance(copied, term.AttVar)
    assert copied is not original
    value, _ = copied.get_attribute('m')
    assert value is copied


def test_copy_term_cycles():
    assert_true('X = f(X), copy_term(X,Y), X == Y.')
    assert_true('X = f(Y,A), Y = g(X,A), copy_term(X,C), '
                'arg(1,C,D), arg(1,D,C), arg(2,C,B), '
                'arg(2,D,B), var(A), var(B), A \\== B.')
    assert_true('X = f(X,A), copy_term(X,C,[]), '
                'arg(1,C,C), arg(2,C,B), var(B), A \\== B.')


def test_findall_and_throw_cycles():
    assert_true('findall(X, X=f(X), [C]), arg(1,C,C).')
    assert_true('catch((X=f(X), throw(X)), C, true), arg(1,C,C).')
    assert_true('X=f(X), catch(atom_chars(X,L), error(type_error(atom,C)), true), '
                'C == X.')
