"""Console presentation and commands for the predicate debugger."""
from prolog.interpreter.trace import TraceObserver, format_goal
from rpyrepl.color import styled


PORT_STYLES = {
    'Call': 'TRACE_CALL',
    'Exit': 'TRACE_EXIT',
    'Redo': 'TRACE_REDO',
    'Fail': 'TRACE_FAIL',
    'Exception': 'TRACE_EXCEPTION',
}


class DebugAbort(Exception):
    """Abort the top-level query, outside Prolog catch/3."""


class ConsoleTraceIO(object):
    def write(self, text):
        from prolog.interpreter.translatedmain import printmessage
        printmessage(text)

    def read_command(self):
        from prolog.interpreter.translatedmain import getch
        return getch()


HELP = """enter/c  creep (next port)
s        skip this call (Call or Redo)
g        show current goal and callers
p        print goal
w        write goal without operators
l        disable tracing and continue (no breakpoints)
a        abort query
h/?      help
Retry and forced failure are not implemented yet.
"""


class ConsoleTraceObserver(TraceObserver):
    def __init__(self):
        self.io = ConsoleTraceIO()

    def event(self, engine, port, frame):
        io = self.io
        label = styled(port + ':', PORT_STYLES[port])
        io.write("%s (%d) %s" % (label, frame.depth, format_goal(engine, frame, port)))
        if port not in engine.debugger.leashed:
            io.write("\n")
            return
        while True:
            io.write(" ? ")
            command = io.read_command()
            if command in ("\n", "\r", "c", ""):
                io.write("\n")
                return
            if command == "s":
                if port in ("Call", "Redo"):
                    engine.debugger.skip_frame = frame
                    io.write("skip\n")
                    return
                io.write("Skip is available at Call and Redo ports.\n")
            elif command == "g":
                caller = frame
                while caller is not None:
                    io.write("\n    [%d] %s" % (
                        caller.depth, format_goal(engine, caller, "Call")))
                    caller = caller.parent
                io.write("\n")
            elif command == "p":
                io.write(format_goal(engine, frame, port) + "\n")
            elif command == "w":
                from prolog.builtin.formatting import TermFormatter
                io.write(TermFormatter(engine, quoted=True, max_depth=20,
                                       ignore_ops=True).format(frame.query) + "\n")
            elif command == "l":
                engine.debugger.disable()
                io.write("Tracing disabled.\n")
                return
            elif command == "a":
                raise DebugAbort
            elif command in ("h", "?"):
                io.write(HELP)
            elif command in ("r", "f"):
                io.write("Retry and forced failure are not implemented yet.\n")
            else:
                io.write("Unknown command; h for help.\n")
