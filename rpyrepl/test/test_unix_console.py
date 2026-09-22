import os
import pytest
from rpyrepl import EndOfInput, make_reader
from rpyrepl.unix_console import UnixConsole, InvalidTerminal
from rpython.rlib import rtermios, rpoll


@pytest.fixture
def console(monkeypatch):
    monkeypatch.setenv('TERM', 'xterm')
    return UnixConsole()


def supply(monkeypatch, console, data):
    chars = iter(data)
    monkeypatch.setattr(os, 'read', lambda fd, count: next(chars, ''))
    monkeypatch.setattr(console, 'getwidth', lambda: 80)
    monkeypatch.setattr(rpoll, 'poll', lambda fds, timeout: [(0, rpoll.POLLIN)])


@pytest.mark.parametrize('data, kind, text', [
    ('\x1b[D', 'left', u''), ('\x1b[C', 'right', u''),
    ('\x1b[A', 'up', u''), ('\x1b[B', 'down', u''),
    ('\x10', 'up', u''), ('\x0e', 'down', u''),
    ('\x1bb', 'backward-word', u''), ('\x1bf', 'forward-word', u''),
    ('\x1b[1;5D', 'backward-word', u''), ('\x1b[1;5C', 'forward-word', u''),
    ('\x1bOd', 'backward-word', u''), ('\x1bOc', 'forward-word', u''),
    ('\x1bd', 'kill-word', u''), ('\x1b\x7f', 'backward-kill-word', u''),
    ('\x1b\x08', 'backward-kill-word', u''), ('\x17', 'backward-kill-word', u''),
    ('\x15', 'unix-line-discard', u''), ('\x0b', 'kill-line', u''),
    ('\x19', 'yank', u''),
    ('\x1b[3~', 'delete', u''), ('\x1b[1;5A', 'unknown', u''),
    ('\x03', 'cancel', u''), ('\x04', 'eof', u''),
    ('\x7f', 'backspace', u''), ('\r', 'accept', u''),
    ('\xc3\xa9', 'text', u'\xe9'), ('\xe7\x95\x8c', 'text', u'\u754c'),
    ('\xf0\x9f\x98\x80', 'text', u'\U0001f600'),
    ('\xed\xa0\x80', 'unknown', u''),
    ('\xf4\x90\x80\x80', 'unknown', u''),
])
def test_events(monkeypatch, console, data, kind, text):
    supply(monkeypatch, console, data)
    event = console.get_event()
    assert (event.evt, event.data) == (kind, text.encode('utf-8'))
    with pytest.raises(EndOfInput):
        console.get_event()


def test_bad_utf8_does_not_swallow_cancel(monkeypatch, console):
    supply(monkeypatch, console, '\xe7\x03')
    assert console.get_event().evt == 'unknown'
    assert console.get_event().evt == 'cancel'


def test_incomplete_escape_times_out(monkeypatch, console):
    supply(monkeypatch, console, '\x1b')
    monkeypatch.setattr(rpoll, 'poll', lambda fds, timeout: [])
    assert console.get_event().evt == 'unknown'


def test_terminal_attributes_restored(monkeypatch, console):
    cc = ['\x00'] * rtermios.NCCS
    cc[rtermios.VERASE] = '\x7f'
    original = (0, 0, 0, rtermios.ECHO | rtermios.ICANON | rtermios.ISIG,
                0, 0, cc)
    changes = []
    monkeypatch.setattr(rtermios, 'tcgetattr', lambda fd: original)
    monkeypatch.setattr(rtermios, 'tcsetattr', lambda fd, when, attrs: changes.append(attrs))
    monkeypatch.setattr(console, 'getwidth', lambda: 80)
    console.prepare()
    assert changes[0][3] & (rtermios.ECHO | rtermios.ICANON | rtermios.ISIG) == 0
    assert changes[0][6][rtermios.VMIN] == '\x01'
    assert original[6][rtermios.VMIN] == '\x00'
    console.restore()
    console.restore()
    assert changes == [changes[0], original]


def test_nonterminal_fallback(monkeypatch):
    monkeypatch.setattr(os, 'isatty', lambda fd: False)
    assert make_reader() is None


def test_dumb_terminal_fallback(monkeypatch):
    monkeypatch.setattr(os, 'isatty', lambda fd: True)
    monkeypatch.setenv('TERM', 'dumb')
    assert make_reader() is None
