from prolog.interpreter.continuation import Engine
from prolog.interpreter.signature import Signature
from prolog.interpreter.test.tool import assert_true, get_engine, prolog_raises


def test_switch_module_invalidates_missing_lookup():
    e = Engine()
    wrapper = e.modulewrapper
    version = wrapper.version
    assert wrapper._get_module("new", version) is None
    e.switch_module("new")
    assert wrapper.version is not version
    assert wrapper._get_module("new", wrapper.version) is wrapper.current_module
    version = wrapper.version
    e.switch_module("user")
    e.switch_module("new")
    assert wrapper.version is version


def test_module_declaration_invalidates_replaced_module():
    e = Engine()
    e.switch_module("m")
    wrapper = e.modulewrapper
    old_module = wrapper.current_module
    version = wrapper.version
    assert wrapper._get_module("m", version) is old_module
    wrapper.add_module("m")
    assert wrapper.version is not version
    assert wrapper._get_module("m", wrapper.version) is wrapper.current_module
    assert wrapper.current_module is not old_module


def test_predicate_definition_and_abolition_invalidate_lookup():
    e = Engine()
    module = e.modulewrapper.current_module
    sig = Signature.getsignature("p", 1)
    version = module.version
    assert module.lookup(sig) is None
    prolog_raises("existence_error(procedure, p/1)", "p(a)", e)
    assert module.version is version
    assert_true("assertz(p(a)).", e)
    first = module.lookup(sig)
    assert first is not None
    assert module.version is not version
    version = module.version
    assert_true("abolish(p/1).", e)
    assert module.version is not version
    assert module.lookup(sig) is None
    version = module.version
    assert_true("abolish(p/1).", e)
    assert module.version is version
    assert_true("asserta(p(b)).", e)
    assert module.version is not version
    assert module.lookup(sig) is not first


def test_clause_and_metadata_changes_preserve_dictionary_version():
    e = get_engine("p(a).")
    module = e.modulewrapper.current_module
    sig = Signature.getsignature("p", 1)
    function = module.lookup(sig)
    version = module.version
    assert_true("assertz(p(b)), asserta(p(c)), "
                "retract(p(a)), retract(p(b)), retract(p(c)).", e)
    assert module.lookup(sig) is function
    assert function.rulechain is None
    assert_true("meta_predicate(p('?')).", e)
    assert_true("assertz(p(d)).", e)
    assert module.lookup(sig) is function
    assert module.version is version


def test_import_invalidates_missing_and_replaced_lookup():
    e = get_engine("", m=":- module(m, [p/1]). p(imported).")
    module = e.modulewrapper.current_module
    imported = e.modulewrapper.modules["m"]
    sig = Signature.getsignature("p", 1)
    assert module.lookup(sig) is None
    version = module.version
    module.use_module(imported)
    assert module.version is not version
    assert module.lookup(sig) is imported.lookup(sig)
    assert_true("abolish(p/1), assertz(p(local)).", e)
    version = module.version
    module.use_module(imported)
    assert module.version is not version
    assert module.lookup(sig) is imported.lookup(sig)
    version = module.version
    module.use_module(imported)
    assert module.version is version
