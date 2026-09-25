"""Enumerate predicate signatures for completion and diagnostics."""


def visible_predicates(engine, module, include_fallbacks=True,
                       include_empty=False):
    from prolog.builtin.register import builtin_signatures
    functions = module.functions.copy()
    system = engine.modulewrapper.system
    if include_fallbacks and system is not None:
        for signature, function in system.functions.iteritems():
            if signature not in functions:
                functions[signature] = function
    signatures = {}
    for signature, function in functions.iteritems():
        if include_empty or function.rulechain is not None:
            signatures[signature.name, signature.numargs] = signature
    if include_fallbacks:
        for signature in builtin_signatures:
            signatures[signature.name, signature.numargs] = signature
    return signatures.values()
