"""
A simple standalone target for the prolog interpreter.
"""

import sys
from prolog.interpreter.translatedmain import run_console

# __________  Entry point  __________

from prolog.interpreter.continuation import Engine, jitdriver
from prolog.interpreter import term
from prolog.interpreter import arithmetic # for side effects
from prolog import builtin # for side effects

from rpython.rlib import jit

e = Engine(load_system=True)
term.DEBUG = False

HELP_TEXT = """Usage: %s [options] [FILE]

Start the interactive Prolog console. If FILE is given, consult it first.

Options:
  -h, --help    Show this help message and exit.
  --jit PARAMS  Set JIT parameters (comma-separated NAME=VALUE, or off).
  --jit help    Show JIT parameters and their defaults, then exit.

Enter halt. or press Ctrl-D to exit the console.
"""


def _make_jit_help():
    lines = ['Advanced JIT options: a comma-separated list of NAME=VALUE:', '']
    for name, value in sorted(jit.PARAMETERS.items()):
        lines.append('  %s=VALUE' % name)
        lines.append('    %s (default %s)' % (jit.PARAMETER_DOCS[name], value))
        lines.append('')
    lines.extend(['  off', '    Turn off the JIT.',
                  '  help', '    Show this help message and exit.'])
    return '\n'.join(lines)


# Build this before translation: PARAMETERS contains both integers and strings.
JIT_HELP_TEXT = _make_jit_help()


def entry_point(argv):
    e.clocks.startup()
    # XXX crappy argument handling
    for i in range(len(argv)):
        if argv[i] == "--jit":
            if len(argv) == i + 1:
                print "missing argument after --jit"
                return 2
            jitarg = argv[i + 1]
            if jitarg == "help":
                print JIT_HELP_TEXT
                return 0
            del argv[i:i+2]
            jit.set_user_param(jitdriver, jitarg)
            break

    for arg in argv[1:]:
        if arg == "--help" or arg == "-h":
            print HELP_TEXT % argv[0]
            return 0

    if len(argv) > 2:
        print "too many arguments"
        return 2
    filename = None
    if len(argv) == 2:
        filename = argv[1]
    run_console(e, filename)
    return 0

# _____ Define and setup target ___


def target(driver, args):
    driver.exe_name = 'pyrolog-%(backend)s'
    return entry_point, None

def portal(driver):
    from prolog.interpreter.portal import get_portal
    return get_portal(driver)

def jitpolicy(self):
    from rpython.jit.codewriter.policy import JitPolicy
    return JitPolicy()

if __name__ == '__main__':
    entry_point(sys.argv)
