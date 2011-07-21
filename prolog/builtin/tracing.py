from prolog.builtin.register import expose_builtin
from prolog.interpreter import continuation

@expose_builtin("trace", unwrap_spec=[], handles_continuation=True)
def impl_trace(engine, heap, scont, fcont):
    engine.tracewrapper.tracing = True
    scont = scont.trace_wrap()
    fcont = fcont.trace_wrap()
    return scont, fcont, heap

@expose_builtin("notrace", unwrap_spec=[], handles_continuation=True)
def impl_notrace(engine, heap, scont, fcont):
    engine.tracewrapper.tracing = False
    scont = scont.trace_unwrap()
    fcont = fcont.trace_unwrap()
    return scont, fcont, heap

