from prolog.builtin.register import expose_builtin
from prolog.interpreter import continuation

@expose_builtin("trace", unwrap_spec=[])
def impl_trace(engine, heap):
    engine.debugger.enable()

@expose_builtin("notrace", unwrap_spec=[])
def impl_notrace(engine, heap):
    engine.debugger.disable()
