import os, sys
import errno
import rpyrepl
from rpyrepl.history import History
from prolog.interpreter.replpolicy import PrologInputPolicy
from prolog.interpreter.highlighting import PrologHighlighter
from rpython.rlib.listsort import TimSort
from rpython.rlib.parsing.parsing import ParseError
from rpython.rlib.parsing.deterministic import LexerError
from prolog.interpreter.parsing import get_query_and_vars
from prolog.interpreter.parsing import get_engine
from prolog.interpreter.continuation import Continuation, Engine, \
        DoneSuccessContinuation, DoneFailureContinuation
from prolog.interpreter import error, term
from prolog.interpreter.error import EndOfInput
from prolog.interpreter.traceconsole import DebugAbort
import prolog.interpreter.term
prolog.interpreter.term.DEBUG = False

helptext = """
 ';':   redo
 'p':   print
 'h':   help
 
"""

class StopItNow(Exception):
    pass


class ContinueContinuation(Continuation):
    def __init__(self, engine, var_to_pos, write):
        Continuation.__init__(self, engine, DoneSuccessContinuation(engine))
        self.var_to_pos = var_to_pos
        self.write = write

    def activate(self, fcont, heap):
        self.write("yes\n")
        var_representation(self.var_to_pos, self.engine, self.write, heap)
        while 1:
            if not fcont.has_choices():
                self.write("\n")
                return DoneSuccessContinuation(self.engine), fcont, heap
            res = getch()
            if res in "\r\x04\n":
                self.write("\n")
                raise StopItNow()
            if res in ";nr":
                raise error.UnificationFailed
            elif res in "h?":
                self.write(helptext)
            elif res in "p":
                var_representation(self.var_to_pos, self.engine, self.write, heap)
            else:
                self.write('unknown action. press "h" for help\n')
                
def var_representation(var_to_pos, engine, write, heap):
    from prolog.builtin import formatting
    f = formatting.TermFormatter(engine, quoted=True, max_depth=20)
    factorizer = formatting.CycleFactorizer()
    names = [name for name in var_to_pos if not name.startswith("_")]
    TimSort(names).sort()
    # Choose names before traversing any answer, including roots reached through
    # another answer. Aliases consistently use the first visible name.
    for name in names:
        value = var_to_pos[name].dereference(heap)
        if isinstance(value, term.Var):
            if value not in f.variable_names:
                f.variable_names[value] = name
        elif isinstance(value, term.Callable) and value.argument_count() > 0:
            if value not in factorizer.preferred:
                label = term.BindingVar()
                factorizer.preferred[value] = label
                f.variable_names[label] = name
    values = [factorizer.visit(var_to_pos[name]) for name in names]
    definitions = {}
    for binding in factorizer.bindings:
        definitions[binding.argument_at(0)] = binding.argument_at(1)
    printed = {}
    for i in range(len(names)):
        name = names[i]
        value = values[i]
        if value in definitions and f.variable_names.get(value) == name:
            printed[value] = None
            value = definitions[value]
        elif (isinstance(value, term.Var) and not isinstance(value, term.AttVar)
              and f.variable_names.get(value) == name):
            continue  # An unconstrained variable needs no X = X equation.
        val = f.format(value)
        if isinstance(value, term.AttVar):
            write("%s\n" % val)
        else:
            write("%s = %s\n" % (name, val))
    for binding in factorizer.bindings:
        label = binding.argument_at(0)
        if label not in printed:
            write("%s = %s\n" % (f.format(label), f.format(binding.argument_at(1))))
        
def getch():
    line = readline()
    return line[0]

def debug(msg):
    os.write(2, "debug: " + msg + '\n')

def printmessage(msg):
    os.write(1, msg)

def readline():
    result = []
    while 1:
        s = os.read(0, 1)
        if s == '':
            if result:
                break
            raise EndOfInput
        result.append(s)
        if s == "\n":
            break
    return "".join(result)

def run(query, var_to_pos, engine):
    #from prolog.builtin import formatting
    #f = formatting.TermFormatter(engine, quoted=True, max_depth=20)
    try:
        if query is None:
            return
        engine.run_query_in_current(
                query,
                ContinueContinuation(engine, var_to_pos, printmessage))
    except error.UnificationFailed:
        printmessage("Nein\n")
    except error.UncaughtError, e:
        printmessage("ERROR:\n%s\n" % e.format_traceback(engine))
    except error.CatchableError, e:
        printmessage("ERROR: %s\n" % e.get_errstr(engine))
    except error.PrologParseError, exc:
        printmessage(exc.message + "\n")
    # except error.UncatchableError, e:
    #     printmessage("INTERNAL ERROR: %s\n" % (e.message, ))
    except StopItNow:
        printmessage("yes\n")
    except DebugAbort:
        printmessage("Execution aborted\n")

def history_filename():
    path = os.environ.get('PYROLOG_HISTORY')
    if path is not None:
        return path
    home = os.environ.get('HOME')
    if home:
        return os.path.join(home, '.pyrolog_history')
    return ''


def repl(engine):
    printmessage("welcome!\n")
    history = History()
    reader = rpyrepl.make_reader(history=history, policy=PrologInputPolicy(),
                                highlighter=PrologHighlighter())
    history_path = history_filename() if reader is not None else ''
    if history_path:
        try:
            history.load(history_path)
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                printmessage('Warning: could not read query history\n')
                history_path = ''
    while 1:
        module = engine.modulewrapper.current_module.name
        if module == "user":
            module = ""
        else:
            module += ":  "
        if engine.debugger.enabled:
            module = "[trace] " + module
        prompt = module + ">?- "
        if reader is None:
            printmessage(prompt)
            line = readline()
        else:
            try:
                line = reader.readline(prompt)
                if line.strip() and (not history.entries or
                                     history.entries[-1] != line):
                    history.append(line)
                    if history_path:
                        try:
                            history.save(history_path)
                        except OSError:
                            printmessage('Warning: could not save query history\n')
            except rpyrepl.EndOfInput:
                raise EndOfInput
            except rpyrepl.CancelledInput:
                printmessage("\n")
                continue
        if line.strip() == "halt.":
            break
        try:
            goals, var_to_pos = engine.parse(line, file_name="<stdin>")
        except error.PrologParseError, exc:
            printmessage(exc.message + "\n")
            continue
        for goal in goals:
            run(goal, var_to_pos, engine)

def execute(e, filename):
    run(term.Callable.build("consult", [term.Callable.build(filename)]), {}, e)


def run_console(engine, filename=None):
    # Keep EOF outside Prolog error handling. In particular, EOF in a traced
    # startup directive must end the session just like EOF at the REPL prompt.
    try:
        if filename is not None:
            execute(engine, filename)
        repl(engine)
    except EndOfInput:
        printmessage("\n")


if __name__ == '__main__':
    from sys import argv
    e = Engine(load_system=True)
    filename = None
    if len(argv) == 2:
        filename = argv[1]
    run_console(e, filename)
