from prolog.builtin.register import expose_builtin
from prolog.interpreter import continuation
from prolog.interpreter.translatedmain import getch, printmessage


@expose_builtin("trace", unwrap_spec=[], handles_continuation=True)
def impl_trace(engine, heap, scont, fcont):
    engine.tracewrapper.tracing = True
    #engine.tracewrapper.write = printmessage
    #engine.tracewrapper.getch = getch
    scont = scont.trace_wrap(1)
    if "query" in dir(scont) and scont.query is not None:
        fcont = fcont.trace_wrap(1, query=scont.query)
    else:
        fcont = fcont.trace_unwrap()
    return scont, fcont, heap

@expose_builtin("notrace", unwrap_spec=[], handles_continuation=True)
def impl_notrace(engine, heap, scont, fcont):
    engine.tracewrapper.tracing = False
    scont = scont.trace_unwrap()
    if "query" in dir(scont) and scont.query is not None:
        fcont = fcont.trace_unwrap(query=scont.query)
    else:
        fcont = fcont.trace_unwrap()
    return scont, fcont, heap

