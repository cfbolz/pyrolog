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
