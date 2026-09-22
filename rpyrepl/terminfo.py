"""Small RPython terminfo bindings; no dependency on PyPy's object space.

As in pypy/module/_minimal_curses/fficurses.py, keep term.h's macros out of
unrelated generated C files by wrapping the functions in a separate module.
"""
from rpython.rtyper.lltypesystem import lltype, rffi
from rpython.translator.tool.cbuild import ExternalCompilationInfo

try:
    eci = ExternalCompilationInfo.from_pkg_config('ncursesw')
except Exception:
    eci = ExternalCompilationInfo(libraries=['ncurses'])
eci = eci.merge(ExternalCompilationInfo(
    post_include_bits=[
        'RPY_EXTERN int rpyrepl_setupterm(char *, int, int *);',
        'RPY_EXTERN char *rpyrepl_tigetstr(char *);',
    ],
    separate_module_sources=['''
#include <curses.h>
#include <term.h>
int rpyrepl_setupterm(char *name, int fd, int *err) {
    return setupterm(name, fd, err);
}
char *rpyrepl_tigetstr(char *name) {
    char *result = tigetstr(name);
    return result == (char *)-1 ? NULL : result;
}
''']))

c_setupterm = rffi.llexternal('rpyrepl_setupterm',
    [rffi.CCHARP, rffi.INT, rffi.INT_realP], rffi.INT, compilation_info=eci)
c_tigetstr = rffi.llexternal('rpyrepl_tigetstr',
    [rffi.CCHARP], rffi.CCHARP, compilation_info=eci)


class InvalidTerminal(Exception):
    pass


def setupterm(name, fd):
    with lltype.scoped_alloc(rffi.INT_realP.TO, 1) as err:
        if c_setupterm(name, fd, err) == -1:
            raise InvalidTerminal


def tigetstr(name, required=False):
    result = c_tigetstr(name)
    if not result:
        if required:
            raise InvalidTerminal
        return ''
    value = rffi.charp2str(result)
    # The first backend does not implement terminfo's padding delays.
    if '$<' in value:
        if required:
            raise InvalidTerminal
        return ''
    return value
