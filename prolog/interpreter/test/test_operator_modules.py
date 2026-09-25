import pytest

from prolog.interpreter.continuation import Engine
from prolog.interpreter.test.tool import assert_true, assert_false, prolog_raises


@pytest.fixture
def operator_library(tmpdir):
    path = tmpdir.join('relations.pl')
    path.write('''
        :- module(relations, [op(500, xfx, likes), pair/1]).
        :- op(300, fx, secret).
        pair(alice likes bob).
    ''')
    return str(path)


def test_export_declares_operator_locally_and_imports_before_next_term(operator_library):
    engine = Engine()
    engine.runstring("""
        :- use_module('%s').
        example(alice likes bob).
    """ % operator_library)
    assert_true('pair(X), example(X), X == likes(alice, bob).', engine)
    assert_true('current_op(500, xfx, likes).', engine)
    assert_false('current_op(_, _, secret).', engine)


def test_operator_import_is_a_copy_and_is_module_local(operator_library):
    engine = Engine()
    engine.runstring("""
        :- module(client, []).
        :- use_module('%s').
        example(alice likes bob).
    """ % operator_library)
    assert_true('example(likes(alice,bob)).', engine)
    assert_false('current_op(_, _, user:likes).', engine)
    assert_true('op(700, xfy, relations:likes), '
                'current_op(500, xfx, likes).', engine)
    assert_true('op(0, xfy, relations:likes), '
                'current_op(500, xfx, likes).', engine)


def test_operator_only_exports_need_no_predicate_and_load_from_library(tmpdir):
    tmpdir.join('syntax.pl').write('''
        :- module(syntax, [op(700, xfx, in), op(450, xfx, ..)]).
    ''')
    engine = Engine()
    assert_true("add_library_dir('%s')." % tmpdir, engine)
    engine.runstring(':- use_module(library(syntax)).\nexample(X in 1..3).')
    assert_true("example(in(x, '..'(1,3))).", engine)


def test_empty_import_list_does_not_import_operators(operator_library):
    engine = Engine()
    assert_true("use_module('%s', [])." % operator_library, engine)
    assert_false('current_op(_, _, likes).', engine)
    assert_true('current_op(500, xfx, relations:likes).', engine)


def test_selective_operator_and_predicate_import(operator_library):
    engine = Engine()
    engine.runstring("""
        :- use_module('%s', [op(500, xfx, likes), pair/1]).
        example(alice likes bob).
    """ % operator_library)
    assert_true('pair(X), example(X).', engine)
    assert_false('current_op(_, _, secret).', engine)


def test_predicate_only_import_does_not_import_operators(operator_library):
    engine = Engine()
    assert_true("use_module('%s', [pair/1]), pair(likes(alice,bob))." %
                operator_library, engine)
    assert_false('current_op(_, _, likes).', engine)


def test_operator_only_import_does_not_import_predicates(operator_library):
    engine = Engine()
    assert_true("use_module('%s', [op(500,xfx,likes)])." % operator_library, engine)
    assert_true('current_op(500,xfx,likes).', engine)
    prolog_raises('existence_error(procedure,_)', 'pair(_)', engine)


@pytest.mark.parametrize('pattern', ['op(P,F,likes)', 'op(P,xfx,N)', 'op(P,F,N)'])
def test_operator_import_patterns_do_not_bind_variables(operator_library, pattern):
    engine = Engine()
    assert_true("use_module('%s', [%s]), var(P), var(F), var(N)." %
                (operator_library, pattern), engine)
    assert_true('current_op(500,xfx,likes).', engine)


@pytest.mark.parametrize('pattern', ['op(P,P,likes)', 'op(600,F,likes)',
                                     'op(P,F,missing)'])
def test_nonmatching_operator_import_patterns(operator_library, pattern):
    engine = Engine()
    assert_true("use_module('%s', [%s]), var(P), var(F)." %
                (operator_library, pattern), engine)
    assert_false('current_op(_,_,likes).', engine)


def test_ground_operator_import_can_override_export(operator_library, capfd):
    engine = Engine()
    assert_true("use_module('%s', [op(600,xfy,likes)])." % operator_library, engine)
    assert_true('current_op(600,xfy,likes).', engine)
    assert 'not exported' in capfd.readouterr()[1]


def test_import_replaces_same_kind_and_preserves_other_kinds(operator_library):
    engine = Engine()
    assert_true('op(700,xfy,likes), op(300,fy,likes).', engine)
    assert_true("use_module('%s')." % operator_library, engine)
    assert_true('current_op(500,xfx,likes), current_op(300,fy,likes).', engine)
    assert_false('current_op(700,xfy,likes).', engine)
    # Import the recorded export, not the exporter's current local definition.
    assert_true('op(800,yfx,relations:likes).', engine)
    assert_true("use_module('%s'), current_op(500,xfx,likes)." %
                operator_library, engine)


def test_export_name_lists_and_multiple_kinds(tmpdir):
    path = tmpdir.join('syntax.pl')
    path.write('''
        :- module(syntax, [op(200,fx,[p,q]), op(300,xfx,p), op(400,yf,p)]).
    ''')
    engine = Engine()
    assert_true("use_module('%s', [op(P,F,[p,q])]), var(P), var(F)." % path, engine)
    assert_true('current_op(200,fx,p), current_op(200,fx,q).', engine)
    assert_false('current_op(_,xfx,p).', engine)
    assert_true("use_module('%s')." % path, engine)
    assert_true('current_op(200,fx,p), current_op(300,xfx,p), '
                'current_op(400,yf,p).', engine)


def test_zero_priority_export_removes_only_its_kind(tmpdir):
    path = tmpdir.join('syntax.pl')
    path.write(':- module(syntax, [op(0,yfx,+)]).')
    engine = Engine()
    assert_true("use_module('%s')." % path, engine)
    assert_false('current_op(_,yfx,+).', engine)
    assert_true('current_op(500,fx,+).', engine)


def test_nested_import_and_reexport(operator_library, tmpdir):
    path = tmpdir.join('middle.pl')
    path.write("""
        :- module(middle, [op(500,xfx,likes), middle_pair/1]).
        :- use_module('%s', [op(_,_,likes), pair/1]).
        middle_pair(X) :- pair(X), X = (alice likes bob).
    """ % operator_library)
    engine = Engine()
    engine.runstring("""
        :- module(client, []).
        :- use_module('%s').
        check :- middle_pair(alice likes bob).
    """ % path)
    assert_true('check.', engine)
    assert_false('current_op(_,_,user:likes).', engine)


@pytest.mark.parametrize('preloaded', [False, True])
def test_qualified_import_targets_calling_module(operator_library, preloaded):
    engine = Engine()
    engine.runstring(':- module(client, []).')
    engine.switch_module('user')
    if preloaded:
        assert_true("use_module('%s', [])." % operator_library, engine)
    assert_true("client:use_module('%s', [op(500,xfx,likes)])." % operator_library,
                engine)
    assert_true('current_op(500,xfx,client:likes).', engine)
    assert_false('current_op(_,_,user:likes).', engine)


def test_imported_operators_used_by_read_and_write(operator_library, tmpdir):
    engine = Engine()
    engine.runstring("""
        :- module(client, []).
        :- use_module('%s').
        output(S) :- write_term(S, likes(alice,bob), [quoted(true)]).
        input(S,X) :- read(S,X).
    """ % operator_library)
    engine.switch_module('user')
    path = tmpdir.join('term.txt')
    assert_true("open('%s',write,S),client:output(S),write(S,'.'),close(S)." %
                path, engine)
    assert path.read() == 'alice likes bob.'
    assert_true("open('%s',read,S),client:input(S,X),close(S),"
                'X == likes(alice,bob).' % path, engine)


@pytest.mark.parametrize('declaration, expected', [
    ('op(P,xfx,p)', 'instantiation_error'),
    ('op(500,F,p)', 'instantiation_error'),
    ('op(500,xfx,N)', 'instantiation_error'),
    ('op(1201,xfx,p)', 'domain_error(operator_priority,1201)'),
    ('op(500,wrong,p)', 'domain_error(operator_specifier,wrong)'),
    ('op(500,xfx,3)', 'type_error(list,3)'),
    ("op(500,xfx,',')", "permission_error(modify,operator,',')"),
    ("op(500,xfx,'|')", "permission_error(create,operator,'|')"),
])
def test_export_validation(declaration, expected):
    engine = Engine()
    prolog_raises(expected, 'module(bad, [%s])' % declaration, engine)
    assert engine.modulewrapper.current_module.name == 'user'
    assert 'bad' not in engine.modulewrapper.modules


def test_bound_export_arguments_are_saved_independently_of_bindings():
    engine = Engine()
    assert_true('(P=500, F=xfx, N=likes, module(relations,[op(P,F,N)]), fail; true).',
                engine)
    engine.switch_module('user')
    assert_true('use_module(relations), current_op(500,xfx,likes).', engine)
