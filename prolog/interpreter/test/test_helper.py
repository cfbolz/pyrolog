from prolog.interpreter.helper import convert_to_str, unwrap_list
from prolog.interpreter.term import Callable, BigInt, BindingVar, Atom
from prolog.interpreter.heap import Heap
from rpython.rlib.rbigint import rbigint
import pytest
from prolog.interpreter import error
from prolog.interpreter.helper import wrap_list, unwrap_char_list

def test_convert_to_str():
    assert "a" == convert_to_str(Callable.build("a"))
    assert "100" == convert_to_str(Callable.build("100"))
    assert "1000.111" == convert_to_str(Callable.build("1000.111"))
    assert ("100000000000000000000" == 
            convert_to_str(Callable.build("100000000000000000000")))
    assert "1" == convert_to_str(BigInt(rbigint.fromint(1)))
    assert ("-1000000000000000" == 
            convert_to_str(BigInt(rbigint.fromdecimalstr("-1000000000000000"))))

def test_unwrap_list():
    a = Callable.build("a")
    l = unwrap_list(Callable.build(".", 
            [a, Callable.build("[]")]))
    assert len(l) == 1
    assert l[0] is a

    v1 = BindingVar()
    a1 = Callable.build("a")
    l1 = unwrap_list(Callable.build(".",
            [v1, Callable.build(".", [a1, Callable.build("[]")])]))
    assert l1 == [v1, a1]

    empty = Callable.build("[]")
    v2 = BindingVar()
    l2 = Callable.build(".", [a, v2])
    v2.unify(empty, Heap())
    unwrapped = unwrap_list(l2)
    assert unwrapped == [a]

    v3 = BindingVar()
    v4 = BindingVar()
    b = Callable.build("b")
    h = Heap()
    l3 = Callable.build(".", [a, v3])
    v3.unify(Callable.build(".", [b, v4]), h)
    v4.unify(Callable.build("[]"), h)
    unwrapped2 = unwrap_list(l3)
    assert unwrapped2 == [a, b]


@pytest.mark.parametrize('prefix, period', [(0, 1), (0, 2), (1, 1),
                                           (3, 7), (64, 1), (1, 65), (129, 131)])
@pytest.mark.parametrize('chars', [False, True])
def test_list_spine_cycles(prefix, period, chars):
    back = BindingVar()
    root = back
    for i in range(period):
        root = Callable.build('.', [Atom.newatom('a'), root])
    back.unify(root, Heap())
    for i in range(prefix):
        root = Callable.build('.', [Atom.newatom('a'), root])
    unwrap = unwrap_char_list if chars else unwrap_list
    with pytest.raises(error.CatchableError) as exc:
        unwrap(root)
    problem = exc.value.term.argument_at(0)
    assert problem.name() == 'type_error'
    assert problem.argument_at(0).name() == 'list'
    assert problem.argument_at(1) is root


@pytest.mark.parametrize('length', [0, 1, 2, 3, 4, 7, 8, 63, 64, 65, 1000])
def test_finite_list_spines(length):
    element = Callable.build('a')
    root = wrap_list([element] * length)
    # Both helpers accept a bound variable as the root as well as in tails.
    bound = BindingVar()
    bound.unify(root, Heap())
    assert unwrap_list(bound) == [element] * length
    assert unwrap_char_list(bound) == ['a'] * length
