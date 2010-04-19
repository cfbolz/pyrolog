from prolog.interpreter.term import Callable, Atom, Number, Var
from prolog.interpreter import helper

def test_predicate_indicator():
    pred_ind = Callable.build("/", [Atom("f"), Number(2)])
    assert helper.unwrap_predicate_indicator(pred_ind).string() == "f/2"
    X = Var()
    X.binding = Atom("g")
    Y = Var()
    Y.binding = Number(3)
    pred_ind = Callable.build("/", [X, Y])
    assert helper.unwrap_predicate_indicator(pred_ind).string() == "g/3"
