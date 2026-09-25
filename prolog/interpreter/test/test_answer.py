import pytest

from prolog.interpreter.answer import format_answer
from prolog.interpreter.continuation import Engine
from prolog.interpreter.helper import unwrap_list
from prolog.interpreter.test.tool import assert_true


@pytest.mark.parametrize('query, expected', [
    ('Goals=[coroutines:when(nonvar(X),user:(Y=done))].',
     'coroutines:when(nonvar(X), user:(Y=done))\n'),
    ('Goals=[put_attr(X,missing,pair(Y,Y))], Z=f(X,Y).',
     'Z = f(X, Y)\nput_attr(X, missing, pair(Y, Y))\n'),
    ('Goals=[put_attr(X,missing,a)], Y=X.',
     'Y = X\nput_attr(X, missing, a)\n'),
    ('Goals=[coroutines:when(nonvar(_Hidden),user:true)].',
     'coroutines:when(nonvar(_G0), user:true)\n'),
    ('X=f(X), Goals=[put_attr(Y,missing,X)].',
     'X = f(X)\nput_attr(Y, missing, X)\n'),
    ('_Cycle=f(_Cycle), Goals=[constraint(_Cycle,_Cycle)].',
     '_G0 = f(_G0)\nconstraint(_G0, _G0)\n'),
    ('put_attr(X,m,a), del_attrs(X), Y=f(X), Goals=[constraint(X)].',
     'Y = f(X)\nconstraint(X)\n'),
    ('Goals=[constraint(_A,_B,_A)].', 'constraint(_G0, _G1, _G0)\n'),
    ('Goals=[], X=Y.', 'Y = X\n'),
    ('Goals=[constraint(X),another(X)].', 'constraint(X)\nanother(X)\n'),
])
def test_format_answer(query, expected):
    engine = Engine()
    bindings = assert_true(query, engine)
    goals = unwrap_list(bindings.pop('Goals'))
    assert format_answer(bindings, goals, engine) == expected
    assert format_answer(bindings, goals, engine) == expected
