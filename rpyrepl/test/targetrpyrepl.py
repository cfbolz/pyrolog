"""Translate independently: rpython --output=rpyrepl-c <this file>."""
import os
import errno
from rpython.rlib import rtermios
from rpyrepl import make_reader, EndOfInput, CancelledInput
from rpyrepl.history import History
from rpyrepl.policy import BalancedParens
from rpyrepl.completion import Completer, Completion


class ExampleCompleter(Completer):
    def complete(self, text, pos):
        start = pos
        while start > 0 and 'a' <= text[start - 1] <= 'z':
            start -= 1
        return Completion(start, ['alpha', 'alphabet', 'alpine', 'beta'])


def entry_point(argv):
    history = History()
    history_path = argv[1] if len(argv) > 1 else ''
    if history_path:
        try:
            history.load(history_path)
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise
    reader = make_reader(history=history, policy=BalancedParens(),
                         completer=ExampleCompleter())
    if reader is None:
        os.write(1, 'plain input\n')
        return 0
    original = rtermios.tcgetattr(0)
    while True:
        try:
            text = reader.readline('edit> ')
        except EndOfInput:
            assert rtermios.tcgetattr(0) == original
            os.write(1, '\nEOF\n')
            return 0
        except CancelledInput:
            assert rtermios.tcgetattr(0) == original
            os.write(1, '\nCANCELLED\n')
            continue
        assert rtermios.tcgetattr(0) == original
        history.append(text)
        if history_path:
            history.save(history_path)
        os.write(1, 'ACCEPTED:' + text + '\n')
        if text == 'quit':
            return 0


def target(driver, args):
    return entry_point, None


if __name__ == '__main__':
    import sys
    sys.exit(entry_point(sys.argv))
