from prolog.builtin.register import expose_builtin
from prolog.interpreter import continuation
from prolog.interpreter import term, error
from prolog.interpreter.helper import unwrap_list

@expose_builtin("trace", unwrap_spec=[], handles_continuation=True)
def impl_trace(engine, heap, scont, fcont):
    engine.tracewrapper.tracing = True
    scont = scont.trace_wrap(1)
    engine.tracewrapper.info("The Debugger will first creep, showing everything (trace).\n\n")
    return scont, fcont, heap

@expose_builtin("notrace", unwrap_spec=[], handles_continuation=True, trace=False)
def impl_notrace(engine, heap, scont, fcont):
    engine.tracewrapper.tracing = False
    scont = scont.trace_unwrap()
    fcont = fcont.trace_unwrap()
    engine.tracewrapper.info("The debugger is switched off.\n")
    return scont, fcont, heap

@expose_builtin("tracing", unwrap_spec=[], trace=False)
def impl_tracing(engine, heap):
    if not engine.tracewrapper.tracing:
        raise error.UnificationFailed

@expose_builtin("leash", unwrap_spec=["obj"], trace=False)
def impl_leash(engine, heap, optionlist):
    if isinstance(optionlist, term.Var):
        error.throw_instantiation_error()
    optionlist = unwrap_list(optionlist)
    for o in optionlist:
        # should always be like +(all), -(fail)
        if o.argument_count() != 1:
            error.throw_domain_error('One of (+|-) all,call,exit,fail,redo,exception', o)
        op = o.name()
        if not op in "+-":
            error.throw_domain_error('One of modifier +,-', o)
        name = o.val_0.name()
        if not name in ['all','call','exit','fail','redo','exception']:
            error.throw_domain_error('One of (+|-) all,call,exit,fail,redo,exception', o)
        if op == "+":
            engine.tracewrapper.add_leash_option(name)
        elif op == "-":
            engine.tracewrapper.remove_leash_option(name)
    leash = list(engine.tracewrapper.leash_options)
    if leash == []:
        engine.tracewrapper.info("No leashing\n")
    else:
        engine.tracewrapper.info("Using leashing stopping at "+repr(leash)+" ports\n")
