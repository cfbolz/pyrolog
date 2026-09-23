import pytest

from prolog.interpreter import error
from prolog.interpreter.continuation import Engine
from prolog.interpreter.test.tool import assert_false, assert_true, get_engine, prolog_raises


def test_retract_variable_body():
    e = get_engine("p(a). p(b) :- q(b).")
    assert_true("findall(pair(X, B), retract((p(X) :- B)), L), "
                "L == [pair(a, true), pair(b, q(b))].", e)


@pytest.mark.parametrize("operation", [
    "assert(M:p(b)), p(b)",
    "asserta(M:p(b)), p(b)",
    "assertz(M:p(b)), p(b)",
    "retract(M:p(a)), \\+ p(a)",
    "abolish(M:p/1), "
    "catch((p(a), fail), error(existence_error(procedure, p/1)), true)",
])
def test_database_bound_module_qualifier(operation):
    e = get_engine("p(a). p(keep).")
    assert_true("M = user, %s." % operation, e)


def test_retract_bound_qualified_pattern():
    e = get_engine("p(a). p(keep).")
    assert_true("P = p(a), retract(user:P), \\+ p(a).", e)


def test_retract_bound_clause_head():
    e = get_engine("p(a). p(keep).")
    assert_true("H = p(a), retract((H :- true)), \\+ p(a).", e)


def test_abolish_bound_predicate_indicator_arguments():
    e = get_engine("p(a).")
    assert_true("Name = p, Arity = 1, abolish(Name/Arity).", e)
    prolog_raises("existence_error(procedure, p/1)", "p(a)", e)


@pytest.mark.parametrize("target, exception", [
    ("1", "type_error(callable, 1)"),
    ("X", "instantiation_error"),
])
def test_retract_invalid_qualified_target(target, exception):
    prolog_raises(exception, "retract(user:%s)" % target)


@pytest.mark.parametrize("builtin", ["assert", "asserta", "assertz"])
def test_assert_invalid_clause_head(builtin):
    prolog_raises("type_error(callable, 1)", "%s((1 :- true))" % builtin)


def test_use_module_parse_error_restores_current_module(tmpdir):
    path = tmpdir.join("broken.pl")
    path.write(":- module(broken, []).\nbad( .\n")
    e = Engine()
    original_module = e.modulewrapper.current_module
    pytest.raises(error.PrologParseError, assert_true,
                  "use_module('%s')." % path, e)
    assert e.modulewrapper.current_module is original_module


def test_use_module_retry_after_missing_file(tmpdir):
    path = tmpdir.join("retry.pl")
    e = Engine()
    prolog_raises("existence_error(source_sink, _)",
                  "use_module('%s')" % path, e)
    path.write(":- module(retry, [loaded/0]).\nloaded.\n")
    assert_true("use_module('%s'), loaded." % path, e)


@pytest.mark.parametrize("clause", ["p(a)", "(p(a) :- true)"])
def test_retract_last_clause_leaves_defined_predicate(clause):
    e = Engine()
    assert_true("assertz(%s), retract(%s)." % (clause, clause), e)
    assert_false("p(_).", e)
    assert_false("retract(p(_)).", e)
    # Neither restoring bindings nor adding a clause changes that distinction.
    assert_true("(assertz(p(b)), retract(p(X)), fail; var(X)).", e)
    assert_false("p(_).", e)
    assert_true("assertz(p(c)), p(c).", e)


def test_abolish_empty_predicate_makes_it_undefined():
    e = Engine()
    assert_true("assertz(p(a)), retract(p(a)).", e)
    assert_false("p(_).", e)
    assert_true("abolish(p/1).", e)
    prolog_raises("existence_error(procedure, p/1)", "p(_)", e)
    assert_true("assertz(p(b)), p(b).", e)


def test_failed_lookup_does_not_define_predicate():
    e = Engine()
    for i in range(2):
        prolog_raises("existence_error(procedure, p/1)", "p(_)", e)
    assert_false("retract(p(_)).", e)
    prolog_raises("existence_error(procedure, p/1)", "p(_)", e)


def test_empty_local_predicate_shadows_system_predicate():
    e = Engine()
    e.switch_module("system")
    e.runstring("p(system).")
    e.modulewrapper.system = e.modulewrapper.current_module
    e.switch_module("user")
    assert_true("p(system).", e)
    assert_true("assertz(p(local)), retract(p(local)).", e)
    assert_false("p(_).", e)
    assert_true("abolish(p/1), p(system).", e)


def test_retract_last_imported_clause_leaves_defined_predicate():
    e = get_engine(":- use_module(m).",
                   m=":- module(m, [p/1]). p(a).")
    assert_true("retract(m:p(a)).", e)
    assert_false("p(_).", e)
    assert_false("m:p(_).", e)
