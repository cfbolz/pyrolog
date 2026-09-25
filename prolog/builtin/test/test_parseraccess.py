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


def test_directive_changes_next_term_and_query():
    e = get_engine(':- op(450,xfy,joins). a joins b. b joins c.')
    assert_true('a joins b.', e)
    assert_true('op(0,xfy,joins).', e)
    from prolog.interpreter.error import PrologParseError
    with pytest.raises(PrologParseError):
        e.parse('a joins b.')


def test_module_switch_changes_parsing_table():
    e = Engine()
    e.runstring(':- module(left, []). :- op(450,xfy,joins). a joins b. '
                ':- module(right, []). :- op(350,yfx,joins). a joins b joins c.')
    assert_true("left:'joins'(a,b), right:'joins'('joins'(a,b),c).", e)
    assert_true('current_op(350,yfx,joins).', e)
    assert_false('current_op(450,xfy,joins).', e)


def test_operator_change_inside_consult(tmpdir):
    path = tmpdir.join('operators.pl')
    path.write(':- op(450,xfy,joins).')
    e = get_engine(" :- consult('%s'). a joins b." % path)
    assert_true('a joins b.', e)


def test_read_and_write_use_calling_module(tmpdir):
    e = get_engine(':- module(left, []). :- op(450,xfy,joins). '
                   'read_it(S,T) :- read(S,T). '
                   'write_it(S,T) :- write_term(S,T,[]). '
                   ':- module(right, []).')
    source = tmpdir.join('input.pl')
    source.write('a joins b.')
    output = tmpdir.join('output.pl')
    assert_true("open('%s',read,S), left:read_it(S,T), close(S), "
                "T = 'joins'(a,b), open('%s',write,W), "
                "left:write_it(W,T), close(W)." % (source, output), e)
    assert output.read() == 'a joins b'
    assert_true("open('%s',read,S), "
                "catch(read(S,_),error(syntax_error(_)),Caught=yes), "
                "Caught==yes, close(S)." % source, e)


@pytest.mark.parametrize('name', ['joins', '\xc3\xa9'])
def test_formatter_uses_current_module(name):
    from prolog.builtin.formatting import TermFormatter
    from prolog.interpreter.parsing import parse_query_term
    e = Engine()
    assert_true('op(450,xfy,%s).' % name, e)
    value = parse_query_term('%s(a,b).' % name)
    assert TermFormatter(e).format(value) == 'a %s b' % name


def test_module_qualified_operator_names():
    e = get_engine(':- module(left, []). :- module(right, []).')
    assert_true('op(450,xfy,left:joins), current_op(450,xfy,left:joins).', e)
    rows = collect_all(e, 'current_op(450,xfy,left:Name).')
    assert [r['Name'].name() for r in rows] == ['joins']
    assert_false('right:current_op(_,_,joins).', e)
    assert_true('op(0,xfy,left:joins).', e)
    assert_false('current_op(_,_,left:joins).', e)


def test_bar_operator_outside_lists():
    e = Engine()
    assert_true("op(1100,xfy,'|').", e)
    assert_true("T = (a|b|c), T = '|'(a,'|'(b,c)).", e)
    assert_true('T = [a|b], T = [a|b].', e)


def test_quoted_operator_name_prints_as_functor():
    from prolog.builtin.formatting import TermFormatter
    from prolog.interpreter.parsing import parse_query_term
    e = Engine()
    assert_true("op(450,xfy,'has space').", e)
    value = parse_query_term("'has space'(a,b).")
    rendered = TermFormatter(e, quoted=True).format(value)
    result = parse_query_term(rendered + '.', e.modulewrapper.current_module.operators)
    assert result.name() == 'has space'
    assert result.argument_count() == 2


@pytest.mark.parametrize('query, expected', [
    ('op(_,xfx,a)', 'instantiation_error'),
    ('op(1,_,a)', 'instantiation_error'),
    ('op(1,xfx,_)', 'instantiation_error'),
    ('op(1.5,xfx,a)', 'type_error(integer,1.5)'),
    ('op(-1,xfx,a)', 'domain_error(operator_priority,-1)'),
    ('op(1201,xfx,a)', 'domain_error(operator_priority,1201)'),
    ('op(1,bad,a)', 'domain_error(operator_specifier,bad)'),
    ('op(1,xfx,42)', 'type_error(list,42)'),
    ('op(1,xfx,f(a))', 'type_error(list,f(a))'),
    ('op(1,xfx,[a,_])', 'instantiation_error'),
    ('op(1,xfx,[42])', 'type_error(atom,42)'),
    ('op(999999999999999999999999,xfx,a)',
     'domain_error(operator_priority,999999999999999999999999)'),
    ("op(1,xfx,',')", "permission_error(modify,operator,',')"),
    ("op(0,fx,'|')", "permission_error(create,operator,'|')"),
    ('current_op(0,_,_)', 'domain_error(operator_priority,0)'),
    ('current_op(_,bad,_)', 'domain_error(operator_specifier,bad)'),
    ('current_op(_,_,42)', 'type_error(atom,42)'),
])
def test_operator_errors(query, expected):
    prolog_raises(expected, query)
