import pytest
from rpyrepl import EndOfInput, CancelledInput
from rpyrepl.console import Console, Event
from rpyrepl.reader import Reader
from rpyrepl.history import History
from rpython.rlib import rutf8


class FakeConsole(Console):
    def __init__(self, events, width=80):
        self.events = list(events)
        self.width = width
        self.screens = []
        self.prepared = False
        self.restored = False
        self.finished = False

    def prepare(self):
        self.prepared = True

    def restore(self):
        self.restored = True

    def get_event(self):
        return self.events.pop(0)

    def refresh(self, screen, cxy):
        self.screens.append((screen, cxy))

    def finish(self):
        self.finished = True


def events(*items):
    return [Event('text', item.encode('utf-8')) if isinstance(item, unicode) else Event(item)
            for item in items]


@pytest.mark.parametrize('keys, expected', [
    (events(u'abc', 'left', 'backspace', u'X', 'accept'), u'aXc'),
    (events('backspace', 'left', 'right', 'delete', 'accept'), u''),
    (events(u'abc', 'home', 'delete', 'end', u'd', 'accept'), u'bcd'),
    (events(u'caf\xe9', 'backspace', u'\u754c', 'accept'), u'caf\u754c'),
    (events(u'a', 'home', 'eof', u'b', 'accept'), u'b'),
])
def test_editing(keys, expected):
    console = FakeConsole(keys)
    reader = Reader(console)
    assert reader.readline('> ') == expected.encode('utf-8')
    assert console.prepared and console.finished and console.restored
    assert 0 <= reader.pos <= len(reader.buffer)


@pytest.mark.parametrize('event, exception', [('eof', EndOfInput),
                                             ('cancel', CancelledInput)])
def test_restore_on_exit(event, exception):
    console = FakeConsole([Event(event)])
    with pytest.raises(exception):
        Reader(console).readline()
    assert console.restored


def test_restore_on_display_failure():
    class BrokenConsole(FakeConsole):
        def refresh(self, screen, cxy):
            raise IOError('write failed')
    console = BrokenConsole([])
    with pytest.raises(IOError):
        Reader(console).readline()
    assert console.restored


def test_restore_on_prepare_failure():
    class BrokenConsole(FakeConsole):
        def prepare(self):
            raise IOError('prepare failed')
    console = BrokenConsole([])
    with pytest.raises(IOError):
        Reader(console).readline()
    assert console.restored


def test_reader_reuse_after_cancellation():
    console = FakeConsole(events(u'old', 'cancel', u'new', 'accept'))
    reader = Reader(console)
    with pytest.raises(CancelledInput):
        reader.readline()
    assert reader.readline() == 'new'


def test_horizontal_scroll_and_return_to_start():
    console = FakeConsole(events(u'abcdefgh', 'home', 'accept'), width=8)
    reader = Reader(console)
    reader.readline('> ')
    assert console.screens[1] == (['> efgh'], (6, 0))
    assert console.screens[2] == (['> abcde'], (2, 0))


def test_unicode_widths():
    console = FakeConsole(events(u'\u754ce\u0301', 'left', 'accept'))
    Reader(console).readline('> ')
    assert console.screens[1] == ([u'> \u754ce\u0301'.encode('utf-8')], (5, 0))
    assert console.screens[2][1] == (5, 0)


def test_unicode_15_emoji_width():
    # SHAKING FACE was added in Unicode 15.0 and occupies two columns.
    console = FakeConsole(events(u'\U0001fae8', 'left', 'accept'))
    Reader(console).readline('> ')
    assert console.screens[1][1] == (4, 0)
    assert console.screens[2][1] == (2, 0)


def test_control_characters_are_not_terminal_commands():
    console = FakeConsole(events(u'\x1b', 'accept'))
    Reader(console).readline()
    assert console.screens[1] == (['^['], (2, 0))


def test_narrow_terminal_and_long_prompt():
    console = FakeConsole(events(u'abcdef', 'accept'), width=2)
    Reader(console).readline('a long prompt> ')
    assert all(len(screen[0]) <= 1 and cxy[0] < 2
               for screen, cxy in console.screens)


def test_unlimited_history():
    history = History()
    entries = [str(i) for i in range(2000)]
    for text in entries:
        history.append(text)
    assert history.entries == entries


@pytest.mark.parametrize('keys, expected', [
    (events('up', 'accept'), u'two'),
    (events('up', 'up', 'up', 'accept'), u'one'),
    (events('up', 'up', 'down', 'accept'), u'two'),
    (events('down', u'draft', 'up', 'down', 'down', 'accept'), u'draft'),
    (events(u'draft', 'left', 'up', 'down', u'!', 'accept'), u'draf!t'),
    (events('up', 'backspace', u'!', 'accept'), u'tw!'),
    (events('up', 'backspace', 'up', 'down', 'accept'), u'two'),
])
def test_history_navigation(keys, expected):
    history = History()
    history.append('one')
    history.append('two')
    reader = Reader(FakeConsole(keys), history)
    assert reader.readline() == expected.encode('utf-8')
    assert history.entries == ['one', 'two']


@pytest.mark.parametrize('history', [None, History()])
def test_empty_history(history):
    reader = Reader(FakeConsole(events(u'draft', 'up', 'down', 'accept')), history)
    assert reader.readline() == 'draft'


def test_history_resets_between_reads():
    history = History()
    history.append('old')
    console = FakeConsole(events(u'draft', 'up', 'cancel',
                                 'up', 'down', 'accept', 'up', 'accept'))
    reader = Reader(console, history)
    with pytest.raises(CancelledInput):
        reader.readline()
    assert reader.readline() == ''
    history.append('new')
    assert reader.readline() == 'new'


@pytest.mark.parametrize('commands, expected', [
    (['left', 'backspace'], u'\xe9\U0001f600'),
    (['home', 'right', 'delete'], u'\xe9\U0001f600'),
    (['left', 'delete'], u'\xe9\u754c'),
    (['backspace'], u'\xe9\u754c'),
    (['home', 'delete'], u'\u754c\U0001f600'),
])
def test_utf8_edit_boundaries(commands, expected):
    keys = events(u'\xe9\u754c\U0001f600', *commands) + events('accept')
    console = FakeConsole(keys)
    reader = Reader(console)
    assert reader.readline() == expected.encode('utf-8')
    rutf8.check_utf8(reader.buffer[:reader.pos], False)
    rutf8.check_utf8(reader.buffer[reader.pos:], False)
    for screen, cxy in console.screens:
        rutf8.check_utf8(screen[0], False)


def test_utf8_history_draft_and_cursor():
    history = History()
    history.append(u'\u754c\U0001f600'.encode('utf-8'))
    console = FakeConsole(events(u'a\xe9z', 'left', 'up', 'down', u'!', 'accept'))
    reader = Reader(console, history)
    assert reader.readline() == u'a\xe9!z'.encode('utf-8')
    assert reader.pos == 4


def test_utf8_scrolling_and_prompt():
    console = FakeConsole(events(u'\xe9\u754c\u754c', 'home', 'accept'), width=8)
    reader = Reader(console)
    reader.readline(u'\xe9> '.encode('utf-8'))
    assert console.screens[1] == ([u'\xe9> \u754c'.encode('utf-8')], (5, 0))
    assert console.screens[2] == ([u'\xe9> \xe9\u754c'.encode('utf-8')], (3, 0))


@pytest.mark.parametrize('bad', ['\x80', '\xc0\xaf', '\xed\xa0\x80',
                                '\xf4\x90\x80\x80', '\xe7\x95'])
def test_invalid_utf8_at_api_boundaries(bad):
    console = FakeConsole([Event('text', bad)])
    with pytest.raises(rutf8.CheckError):
        Reader(console).readline()
    assert console.restored
    with pytest.raises(rutf8.CheckError):
        Reader(FakeConsole([])).readline(bad)
    history = History()
    with pytest.raises(rutf8.CheckError):
        history.append(bad)
    assert history.entries == []
