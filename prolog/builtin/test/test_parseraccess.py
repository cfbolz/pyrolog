import pytest

from prolog.interpreter.continuation import Engine
from prolog.interpreter.parsing import get_engine
from prolog.interpreter.test.tool import assert_true, assert_false, collect_all, prolog_raises


def test_declare_replace_and_remove_by_kind():
    e = Engine()
    assert_true("op(300,fy,testop), op(500,xfy,testop).", e)
    assert_true("op(400,yfx,testop), current_op(300,fy,testop), "
                "current_op(400,yfx,testop).", e)
    assert_false("current_op(500,xfy,testop).", e)
    assert_true("op(0,xfy,testop), op(0,yfx,testop), current_op(300,fy,testop).", e)
    assert_false("current_op(_,yfx,testop).", e)


def test_current_op_backtracks_without_duplicate_bindings():
    e = Engine()
    assert_true("op(300,fy,testop), op(500,xfy,testop).", e)
    rows = collect_all(e, 'current_op(P,F,testop).')
    assert sorted((r['P'].num, r['F'].name()) for r in rows) == [(300,'fy'), (500,'xfy')]
    assert_true('current_op(500,F,testop), F=xfy.', e)


def test_operator_changes_survive_backtracking():
    e = Engine()
    assert_false('op(500,xfx,testop), fail.', e)
    assert_true('current_op(500,xfx,testop).', e)


def test_operator_names_list_and_bound_arguments():
    e = Engine()
    assert_true('P=500, F=xfx, A=first, Names=[A,second], op(P,F,Names).', e)
    assert_true('current_op(500,xfx,first), current_op(500,xfx,second), op(500,xfx,[]).', e)


def test_calling_module_owns_operators():
    e = get_engine(':- module(left, []). declare :- op(500,xfx,testop). '
                   ':- module(right, []).')
    assert_true('left:declare, left:current_op(500,xfx,testop).', e)
    assert_false('right:current_op(_,_,testop).', e)
    assert_false('current_op(_,_,testop).', Engine())


@pytest.mark.parametrize('query, expected', [
    ('op(_,xfx,a)', 'instantiation_error'),
    ('op(1,_,a)', 'instantiation_error'),
    ('op(1,xfx,_)', 'instantiation_error'),
    ('op(1.5,xfx,a)', 'type_error(integer,1.5)'),
    ('op(-1,xfx,a)', 'domain_error(operator_priority,-1)'),
    ('op(1201,xfx,a)', 'domain_error(operator_priority,1201)'),
    ('op(1,bad,a)', 'domain_error(operator_specifier,bad)'),
    ('op(1,xfx,42)', 'type_error(atom,42)'),
    ("op(1,xfx,',')", "permission_error(modify,operator,',')"),
    ('current_op(0,_,_)', 'domain_error(operator_priority,0)'),
    ('current_op(_,bad,_)', 'domain_error(operator_specifier,bad)'),
    ('current_op(_,_,42)', 'type_error(atom,42)'),
])
def test_operator_errors(query, expected):
    prolog_raises(expected, query)
