import pytest
from rpyrepl import EndOfInput, CancelledInput
from rpyrepl.console import Console, Event
from rpyrepl.reader import Reader
from rpyrepl.history import History


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
    return [Event('text', item) if isinstance(item, unicode) else Event(item)
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
    assert reader.readline(u'> ') == expected
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
    assert reader.readline() == u'new'


def test_horizontal_scroll_and_return_to_start():
    console = FakeConsole(events(u'abcdefgh', 'home', 'accept'), width=8)
    reader = Reader(console)
    reader.readline(u'> ')
    assert console.screens[1] == ([u'> efgh'], (6, 0))
    assert console.screens[2] == ([u'> abcde'], (2, 0))


def test_unicode_widths():
    console = FakeConsole(events(u'\u754ce\u0301', 'left', 'accept'))
    Reader(console).readline(u'> ')
    assert console.screens[1] == ([u'> \u754ce\u0301'], (5, 0))
    assert console.screens[2][1] == (5, 0)


def test_control_characters_are_not_terminal_commands():
    console = FakeConsole(events(u'\x1b', 'accept'))
    Reader(console).readline()
    assert console.screens[1] == ([u'^['], (2, 0))


def test_narrow_terminal_and_long_prompt():
    console = FakeConsole(events(u'abcdef', 'accept'), width=2)
    Reader(console).readline(u'a long prompt> ')
    assert all(len(screen[0]) <= 1 and cxy[0] < 2
               for screen, cxy in console.screens)


def test_bounded_history():
    history = History(2)
    for text in [u'first', u'second', u'third']:
        history.append(text)
    assert history.entries == [u'second', u'third']


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
    history.append(u'one')
    history.append(u'two')
    reader = Reader(FakeConsole(keys), history)
    assert reader.readline() == expected
    assert history.entries == [u'one', u'two']


@pytest.mark.parametrize('history', [None, History()])
def test_empty_history(history):
    reader = Reader(FakeConsole(events(u'draft', 'up', 'down', 'accept')), history)
    assert reader.readline() == u'draft'


def test_history_resets_between_reads():
    history = History()
    history.append(u'old')
    console = FakeConsole(events(u'draft', 'up', 'cancel',
                                 'up', 'down', 'accept', 'up', 'accept'))
    reader = Reader(console, history)
    with pytest.raises(CancelledInput):
        reader.readline()
    assert reader.readline() == u''
    history.append(u'new')
    assert reader.readline() == u'new'
