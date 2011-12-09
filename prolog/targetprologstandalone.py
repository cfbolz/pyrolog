"""
A simple standalone target for the prolog interpreter.
"""

import sys, os
from prolog.interpreter.translatedmain import repl, execute

# __________  Entry point  __________

from prolog.interpreter.continuation import Engine, jitdriver
from prolog.interpreter import term
from prolog.interpreter import arithmetic # for side effects
from prolog import builtin # for side effects

from pypy.rlib import jit

e = Engine(load_system=True)
term.DEBUG = False

def entry_point(argv):
    d = {}
    try:
        fd = os.open("prolog-shapes", os.O_RDONLY, 0777)
    except OSError:
        pass
    else:
        try:
            content = []
            while 1:
                s = os.read(fd, 4096)
                if not s:
                    break
                content.append(s)
            file_content = "".join(content)
        finally:
            os.close(fd)
        for line in file_content.splitlines():
            if line:
                shape, functor, count = line.split(" ")
                d[shape, functor] = int(count)
    from prolog.interpreter import specialterm
    specialterm.stats.d = d

    e.clocks.startup()
    # XXX crappy argument handling
    for i in range(len(argv)):
        if argv[i] == "--jit":
            if len(argv) == i + 1:
                print "missing argument after --jit"
                return 2
            jitarg = argv[i + 1]
            del argv[i:i+2]
            jit.set_user_param(jitdriver, jitarg)
            break

    if len(argv) == 2:
        execute(e, argv[1])
    if len(argv) > 2:
        print "too many arguments"
        return 2
    retval = 0
    try:
        repl(e)
    except SystemExit:
        retval = 1

    try:
        fd = os.open("prolog-shapes", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0777)
    except OSError, x:
        print "OSError", x
    else:
        try:
            for (shape, functor), value in d.iteritems():
                if len(functor.split(" ")) > 1:
                    print "discarding", functor
                    continue
                os.write(fd, "%s %s %s\n" % (shape, functor, value))
        finally:
            os.close(fd)
    return retval

# _____ Define and setup target ___


def target(driver, args):
    driver.exe_name = 'pyrolog-%(backend)s'
    return entry_point, None

def portal(driver):
    from prolog.interpreter.portal import get_portal
    return get_portal(driver)

def jitpolicy(self):
    from pypy.jit.codewriter.policy import JitPolicy
    return JitPolicy()

if __name__ == '__main__':
    entry_point(sys.argv)
