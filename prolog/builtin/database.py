from prolog.interpreter import helper, term, error, continuation
from prolog.interpreter.signature import Signature
from prolog.interpreter.module import VersionTag
from prolog.builtin.register import expose_builtin

# ___________________________________________________________________
# database

prefixsig = Signature.getsignature(":", 2)
implsig = Signature.getsignature(":-", 2)
TRUE_ATOM = term.Callable.build("true")

def unpack_modname_and_predicate(rule):
    mod = rule.argument_at(0).dereference(None)
    if helper.is_numeric(mod):
        error.throw_domain_error("atom", mod)
        assert 0, "unreachable"
    indicator = rule.argument_at(1)
    if not isinstance(mod, term.Atom):
        raise error.UnificationFailed()
        assert 0, "unreachable"
    return mod.name(), indicator

@expose_builtin("abolish", unwrap_spec=["callable"], needs_module=True)
def impl_abolish(engine, heap, module, predicate):
    modname = None
    if predicate.signature().eq(prefixsig):
        modname, predicate = unpack_modname_and_predicate(predicate)
    name, arity = helper.unwrap_predicate_indicator(predicate)
    if arity < 0:
        error.throw_domain_error("not_less_than_zero", term.Number(arity))
    signature = Signature.getsignature(name, arity)
    if signature.get_extra("builtin"):
        error.throw_permission_error("modify", "static_procedure",
                                     predicate)
    if modname is not None:
        module = engine.modulewrapper.get_module(modname, predicate)
    try:
        del module.functions[signature]
    except KeyError:
        pass
    else:
        module.version = VersionTag()
    module.meta_predicates.pop(signature, None)

@expose_builtin(["assert", "assertz"], unwrap_spec=["callable"],
        needs_module=True)
def impl_assert(engine, heap, module, rule):
    handle_assert(engine, heap, module, rule, True)

@expose_builtin("asserta", unwrap_spec=["callable"], needs_module=True)
def impl_asserta(engine, heap, module, rule):
    handle_assert(engine, heap, module, rule, False)

def handle_assert(engine, heap, module, rule, end):
    m = engine.modulewrapper
    current_modname = m.current_module.name
    try:
        engine.switch_module(module.name)
        if rule.signature().eq(prefixsig):
            modname, rule = unpack_modname_and_predicate(rule)
            engine.switch_module(modname)
        engine.add_rule(rule.dereference(heap), end=end)
    finally:
        engine.switch_module(current_modname)

@expose_builtin("retract", unwrap_spec=["callable"], needs_module=True,
                handles_continuation=True)
def impl_retract(engine, heap, module, pattern, scont, fcont):
    modname = None
    if pattern.signature().eq(prefixsig):
        modname, pattern = unpack_modname_and_predicate(pattern)
    pattern = helper.ensure_callable(pattern.dereference(heap))
    if helper.is_term(pattern) and pattern.signature().eq(implsig):
        head = helper.ensure_callable(pattern.argument_at(0).dereference(heap))
        body = pattern.argument_at(1).dereference(heap)
        if not isinstance(body, term.Var):
            helper.ensure_callable(body)
    else:
        head = pattern
        body = TRUE_ATOM
    assert isinstance(head, term.Callable)
    if head.signature().get_extra("builtin"):
        error.throw_permission_error("modify", "static_procedure", 
                                     head.get_prolog_signature())
    if modname is None:
        function = module.lookup(head.signature())
    else:
        function = engine.modulewrapper.get_module(modname,
                pattern).lookup(head.signature())
    if function is None or function.rulechain is None:
        raise error.UnificationFailed
    return continue_retract(engine, scont, fcont, heap, function,
                            function.rulechain, head, body)


@continuation.make_failure_continuation
def continue_retract(Choice, engine, scont, fcont, heap,
                     function, rulechain, head, body):
    candidate_heap = heap.branch()
    while rulechain:
        rule = rulechain
        # standardizing apart
        try:
            deleted_body = rule.clone_and_unify_head(candidate_heap, head)
            if deleted_body is None:
                deleted_body = TRUE_ATOM
            body.unify(deleted_body, candidate_heap)
        except error.UnificationFailed:
            candidate_heap.revert_upto(heap)
        except error.CatchableError, exc:
            candidate_heap.revert_upto(heap)
            return engine.throw(exc, scont, fcont, heap)
        else:
            function.remove(rulechain)
            if rulechain.next is not None:
                fcont = Choice(engine, scont, fcont, heap, function,
                               rulechain.next, head, body)
            break
        rulechain = rulechain.next
    else:
        # On retry this helper is called from fcont.fail(), outside the
        # driver's exception handler. Resume the caller's failure directly.
        return fcont.fail(heap)
    # Continue on the matching frame so its bindings and queued hooks remain
    # part of execution, and outer backtracking can undo the bindings.
    return scont, fcont, candidate_heap
