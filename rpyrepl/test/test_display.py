"""Exercise repaint output against a small terminal model, including scrolling."""
import re
from rpyrepl.unix_console import UnixConsole


class Terminal(object):
    def __init__(self, width=10, height=3):
        self.width, self.height = width, height
        self.lines = [[' '] * width for i in range(height)]
        self.x, self.y = 0, height - 1
        self.pending_wrap = False

    def newline(self):
        self.y += 1
        if self.y == self.height:
            self.lines.pop(0)
            self.lines.append([' '] * self.width)
            self.y -= 1

    def write(self, data):
        while data:
            if data.startswith('\x1b['):
                match = re.match('\x1b\\[([0-9;]*)([A-Z])', data)
                assert match, repr(data)
                number, command = match.groups()
                count = int(number or '1')
                self.pending_wrap = False
                if command == 'A':
                    self.y = max(0, self.y - count)
                elif command == 'B':
                    self.y = min(self.height - 1, self.y + count)
                elif command == 'C':
                    self.x = min(self.width - 1, self.x + count)
                elif command == 'K':
                    self.lines[self.y][self.x:] = [' '] * (self.width - self.x)
                elif command == 'H':
                    self.x, self.y = 0, 0
                elif command == 'J':
                    assert number == '2'
                    self.lines = [[' '] * self.width for i in range(self.height)]
                else:
                    assert False, command
                data = data[match.end():]
                continue
            char, data = data[0], data[1:]
            if char == '\r':
                self.x = 0
                self.pending_wrap = False
            elif char == '\n':
                self.newline()
                self.pending_wrap = False
            else:
                if self.pending_wrap:
                    self.x = 0
                    self.newline()
                self.lines[self.y][self.x] = char
                self.pending_wrap = self.x == self.width - 1
                self.x = min(self.width - 1, self.x + 1)

    def screen(self):
        return [''.join(line).rstrip() for line in self.lines]


def make_console(monkeypatch):
    monkeypatch.setenv('TERM', 'xterm')
    console = UnixConsole()
    terminal = Terminal()
    console.width, console.height = terminal.width, terminal.height
    console.up, console.down, console.right = '\x1b[A', '\x1b[B', '\x1b[C'
    console.cr, console.el, console.clear = '\r', '\x1b[K', '\x1b[H\x1b[2J'
    console.reset_display()
    console.write = terminal.write
    return console, terminal


def test_grow_shrink_and_finish_from_upper_row(monkeypatch):
    console, terminal = make_console(monkeypatch)
    console.refresh(['> abcdefg\\', 'hij', '.. third'], (2, 1))
    assert terminal.screen() == ['> abcdefg\\', 'hij', '.. third']
    assert (terminal.x, terminal.y) == (2, 1)
    console.refresh(['> a', '.. b'], (2, 0))
    assert terminal.screen() == ['> a', '.. b', '']
    console.finish()
    assert (terminal.x, terminal.y) == (0, 2)


def test_vertical_viewport_and_resize(monkeypatch):
    console, terminal = make_console(monkeypatch)
    rows = ['line' + str(i) for i in range(6)]
    console.refresh(rows, (3, 5))
    assert terminal.screen() == rows[3:]
    assert (terminal.x, terminal.y) == (3, 2)
    console.refresh(rows, (2, 0))
    assert terminal.screen() == rows[:3]
    assert (terminal.x, terminal.y) == (2, 0)
    console.width = terminal.width = 12
    console.refresh(['new width'], (4, 0))
    assert terminal.screen() == ['new width', '', '']
    assert (terminal.x, terminal.y) == (4, 0)
