import os, sys
import errno
import rpyrepl
from rpyrepl.history import History
from rpyrepl.color import styled
from prolog.interpreter.replpolicy import PrologInputPolicy
from prolog.interpreter.highlighting import PrologHighlighter
from prolog.interpreter.completion import PrologCompleter
from prolog.interpreter.answer import format_answer
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
        from prolog.builtin.attvars import attributed_variables, copy_term_with_attributes
        from prolog.interpreter.helper import wrap_list
        names = self.var_to_pos.keys()
        values = wrap_list([self.var_to_pos[name] for name in names])
        variables = attributed_variables(self.engine, heap, values)
        if not variables:
            # Formatting is read-only. Avoid the recursive copier for ordinary
            # answers, including deep terms that the formatter will truncate.
            display = DisplayAnswerContinuation(self.engine, names, values,
                                                wrap_list([]), self.write)
            return display, fcont, heap
        copied = heap.newvar()
        goals = heap.newvar()
        display = DisplayAnswerContinuation(self.engine, names, copied,
                                            goals, self.write)
        return copy_term_with_attributes(self.engine, heap, values, copied,
                                         goals, variables, display, fcont)


class DisplayAnswerContinuation(Continuation):
    def __init__(self, engine, names, copied, goals, write):
        Continuation.__init__(self, engine, DoneSuccessContinuation(engine))
        self.names = names
        self.copied = copied
        self.goals = goals
        self.write = write

    def activate(self, fcont, heap):
        from prolog.interpreter.helper import unwrap_list
        values = unwrap_list(self.copied)
        variables = {}
        for i in range(len(self.names)):
            variables[self.names[i]] = values[i]
        goals = unwrap_list(self.goals)
        answer = format_answer(variables, goals, self.engine)
        self.write("yes\n")
        self.write(answer)
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
                self.write(answer)
            else:
                self.write('unknown action. press "h" for help\n')
                
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

def run(query, var_to_pos, engine, query_source=None):
    #from prolog.builtin import formatting
    #f = formatting.TermFormatter(engine, quoted=True, max_depth=20)
    try:
        if query is None:
            return
        engine.run_query_in_current(
                query,
                ContinueContinuation(engine, var_to_pos, printmessage))
    except error.UnificationFailed:
        printmessage(styled('Nein', 'FAILURE') + '\n')
    except error.UncaughtError, e:
        printmessage("%s\n%s\n" % (styled('ERROR:', 'ERROR_LABEL'),
                                      e.format_traceback(engine, query_source=query_source)))
    except error.CatchableError, e:
        printmessage("ERROR: %s\n" % e.get_errstr(engine))
    except error.PrologParseError, exc:
        printmessage(exc.format_message() + "\n")
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
                                highlighter=PrologHighlighter(),
                                completer=PrologCompleter(engine))
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
        except error.CatchableError, exc:
            printmessage("ERROR: %s\n" % exc.get_errstr(engine))
            continue
        except error.PrologParseError, exc:
            printmessage(exc.format_message() + "\n")
            continue
        for goal in goals:
            run(goal, var_to_pos, engine, query_source=line)

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
