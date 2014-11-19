import py
import os
from prolog.interpreter.test.tool import get_engine, assert_true, assert_false, prolog_raises
from prolog.interpreter.test.tool import create_file, delete_file, create_dir, delete_dir
from prolog.interpreter.test.tool import collect_all
from prolog.interpreter import term
from prolog.interpreter.signature import Signature
from prolog.interpreter.continuation import Engine
from prolog.interpreter.error import UncaughtError

# needs list module
def test_access_system_predicate():
    e = get_engine("""
        make_list(A, B) :- make_list(A, [], B).
        make_list(X, In, Out) :-
            X > 0,
            X0 is X - 1,
            make_list(X0, [X|In], Out).
        make_list(0, In, In).
    """, load_system=True)
    assert_true("Len = 400, Len0 is Len - 5, make_list(Len, L), append(L1, _, L), length(L1, Len0).", e)
