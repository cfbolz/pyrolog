import pytest
from rpyrepl import EndOfInput
from rpyrepl.console import Event
from rpyrepl.reader import Reader
from rpyrepl.test.test_reader import FakeConsole, events
from rpyrepl.test.test_unix_console import console, supply


@pytest.mark.parametrize('payload, expected', [
    ('', ''),
    ('a\rb\r\nc\nd', 'a\nb\nc\nd'),
    ('\r\r\n\n', '\n\n\n'),
    ('\x03\x04\x7f\t\x12\x1b[D', '\x03\x04\x7f\t\x12\x1b[D'),
    ('\x1b\x1b[201x\x1b[200~', '\x1b\x1b[201x\x1b[200~'),
    (u'caf\xe9\n\u754c'.encode('utf-8'), u'caf\xe9\n\u754c'.encode('utf-8')),
    ('x' * 10000, 'x' * 10000),
])
def test_paste_is_one_event(monkeypatch, console, payload, expected):
    # supply feeds one byte per read, including both delimiter sequences.
    supply(monkeypatch, console, '\x1b[200~' + payload + '\x1b[201~\r')
    event = console.get_event()
    assert (event.evt, event.data) == ('paste', expected)
    assert console.get_event().evt == 'accept'


@pytest.mark.parametrize('payload', ['\xff', '\xed\xa0\x80', '\xc3'])
def test_invalid_utf8_paste_is_discarded(monkeypatch, console, payload):
    supply(monkeypatch, console, '\x1b[200~' + payload + '\x03\r\x1b[201~x')
    assert console.get_event().evt == 'unknown'
    event = console.get_event()
    assert (event.evt, event.data) == ('text', 'x')


def test_incomplete_paste_eof(monkeypatch, console):
    supply(monkeypatch, console, '\x1b[200~unfinished\x1b[20')
    with pytest.raises(EndOfInput):
        console.get_event()


def test_paste_inserts_at_cursor_without_accepting():
    console = FakeConsole(events(u'ab', 'left') +
                          [Event('paste', 'one\ntwo\n\x03\x04\x1b[D')] +
                          events('force-accept'))
    reader = Reader(console)
    assert reader.readline() == 'aone\ntwo\n\x03\x04\x1b[Db'
    assert len(console.screens) == 4
    assert '^C^D^[[D' in ''.join(console.screens[-1][0])


def test_paste_exits_search_and_edits_match():
    console = FakeConsole(events(u'abc', 'reverse-search', u'b') +
                          [Event('paste', 'X\n')] + events('force-accept'))
    reader = Reader(console)
    assert reader.readline() == 'aX\nbc'
    assert reader.search is None
