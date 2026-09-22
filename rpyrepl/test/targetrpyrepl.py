"""Translate independently: rpython --output=rpyrepl-c <this file>."""
import os
from rpython.rlib import rtermios
from rpyrepl import make_reader, EndOfInput, CancelledInput


def entry_point(argv):
    reader = make_reader()
    if reader is None:
        os.write(1, 'plain input\n')
        return 0
    original = rtermios.tcgetattr(0)
    while True:
        try:
            text = reader.readline(u'edit> ')
        except EndOfInput:
            assert rtermios.tcgetattr(0) == original
            os.write(1, '\nEOF\n')
            return 0
        except CancelledInput:
            assert rtermios.tcgetattr(0) == original
            os.write(1, '\nCANCELLED\n')
            continue
        assert rtermios.tcgetattr(0) == original
        os.write(1, 'ACCEPTED:' + text.encode('utf-8') + '\n')
        if text == u'quit':
            return 0


def target(driver, args):
    return entry_point, None


if __name__ == '__main__':
    import sys
    sys.exit(entry_point(sys.argv))
