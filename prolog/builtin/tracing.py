from prolog.builtin.register import expose_builtin
from prolog.interpreter import continuation
from prolog.interpreter import error, helper, term

@expose_builtin("trace", unwrap_spec=[])
def impl_trace(engine, heap):
    engine.debugger.enable()

@expose_builtin("notrace", unwrap_spec=[])
def impl_notrace(engine, heap):
    engine.debugger.disable()


@expose_builtin("tracing", unwrap_spec=[])
def impl_tracing(engine, heap):
    if not engine.debugger.enabled:
        raise error.UnificationFailed


@expose_builtin("leash", unwrap_spec=["list"])
def impl_leash(engine, heap, options):
    # Validate first, so an invalid option does not partially change the mode.
    changes = []
    for option in options:
        option = option.dereference(heap)
        if isinstance(option, term.Var):
            error.throw_instantiation_error()
        if (not isinstance(option, term.Callable) or
                option.argument_count() != 1 or option.name() not in ("+", "-")):
            error.throw_domain_error("leash_option", option)
        value = option.argument_at(0).dereference(heap)
        if isinstance(value, term.Var):
            error.throw_instantiation_error()
        name = helper.unwrap_atom(value)
        if name not in ("all", "call", "exit", "redo", "fail", "exception"):
            error.throw_domain_error("trace_port", value)
        changes.append((option.name() == "+", name))
    ports = ["Call", "Exit", "Redo", "Fail", "Exception"]
    for add, name in changes:
        for port in ports:
            if name == "all" or name == port.lower():
                if add:
                    engine.debugger.leashed[port] = True
                elif port in engine.debugger.leashed:
                    del engine.debugger.leashed[port]
