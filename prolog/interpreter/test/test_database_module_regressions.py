import pytest

from prolog.interpreter import error
from prolog.interpreter.continuation import Engine
from prolog.interpreter.test.tool import assert_true, get_engine, prolog_raises


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
