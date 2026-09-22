import pytest
from rpyrepl import EndOfInput, CancelledInput
from rpyrepl.console import Console, Event
from rpyrepl.reader import Reader


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
