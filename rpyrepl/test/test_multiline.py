import pytest
from rpyrepl.console import Event
from rpyrepl.history import History
from rpyrepl.layout import Layout
from rpyrepl.policy import BalancedParens
from rpyrepl.reader import Reader
from rpyrepl.test.test_reader import FakeConsole, events


def test_layout_newlines_and_wrapping():
    layout = Layout('abcdefghij\nx\n', 8, '> ', '.. ')
    assert layout.screen == ['> abcde\\', 'fghij', '.. x', '.. ']
    for pos in range(14):
        x, y = layout.pos_to_xy(pos)
        assert layout.xy_to_pos(x, y) == pos


def test_utf8_layout_boundaries():
    text = u'\xe9\u754ce\u0301\n\U0001fae8'.encode('utf-8')
    layout = Layout(text, 7, '> ', '.. ')
    assert layout.screen == [u'> \xe9\u754ce\u0301'.encode('utf-8'),
                             u'.. \U0001fae8'.encode('utf-8')]
    assert layout.pos_to_xy(2) == (3, 0)
    assert layout.pos_to_xy(5) == (5, 0)
    assert layout.pos_to_xy(8) == (6, 0)
    assert layout.pos_to_xy(9) == (3, 1)
    # Clicking in a wide character stays on a valid boundary before it.
    assert layout.xy_to_pos(4, 0) == 2
    assert layout.xy_to_pos(6, 0) == 8


def test_tiny_widths_progress():
    for width in range(1, 6):
        layout = Layout(u'\u754c\x1b\n\u754c'.encode('utf-8'), width, 'long prompt', 'long')
        assert len(layout.rows) <= 5
        assert layout.pos_to_xy(8)[1] == len(layout.rows) - 1
        if width == 1:
            assert all(len(row) <= 1 for row in layout.screen)


def test_enter_and_force_accept():
    console = FakeConsole(events(u'(', 'accept', u')', 'accept'))
    reader = Reader(console, policy=BalancedParens())
    assert reader.readline('> ', '.. ') == '(\n)'
    assert console.screens[2] == (['> (', '.. '], (3, 1))
    reader = Reader(FakeConsole(events(u'(', 'force-accept')), policy=BalancedParens())
    assert reader.readline() == '('


def test_enter_in_earlier_line_inserts_newline():
    console = FakeConsole(events(u'a\nb', 'up', 'accept', 'force-accept'))
    assert Reader(console).readline('', '') == 'a\n\nb'


def test_vertical_preferred_column():
    reader = Reader(FakeConsole([]))
    reader.buffer = 'abcdef\nx\nabcdef'
    reader.continuation_prompt = ''
    reader.pos = 4
    reader.do_cmd(Event('down'))
    assert reader.pos == 8
    reader.do_cmd(Event('down'))
    assert reader.pos == 13
    reader.do_cmd(Event('left'))
    reader.do_cmd(Event('up'))
    reader.do_cmd(Event('up'))
    assert reader.pos == 3


def test_wrapped_rows_before_history():
    history = History()
    history.append('old\nentry')
    reader = Reader(FakeConsole([], width=8), history)
    reader.buffer = 'abcdefghij'
    reader.pos = 9
    reader.history_index = 1
    reader.do_cmd(Event('up'))
    assert reader.buffer == 'abcdefghij'
    assert reader.pos == 2
    reader.do_cmd(Event('up'))
    assert reader.buffer == 'old\nentry'
    reader.do_cmd(Event('next-history'))
    assert reader.buffer == 'abcdefghij'
    assert reader.pos == 2
    reader.do_cmd(Event('previous-history'))
    assert reader.buffer == 'old\nentry'


@pytest.mark.parametrize('command, pos, expected, expected_pos', [
    ('home', 6, 'abc\ndef', 4), ('end', 1, 'abc\ndef', 3),
    ('backspace', 4, 'abcdef', 3), ('delete', 3, 'abcdef', 3),
    ('unix-line-discard', 6, 'abc\nf', 4),
    ('kill-line', 1, 'a\ndef', 1), ('kill-line', 3, 'abcdef', 3),
])
def test_logical_line_commands(command, pos, expected, expected_pos):
    reader = Reader(FakeConsole([]))
    reader.buffer, reader.pos = 'abc\ndef', pos
    reader.do_cmd(Event(command))
    assert (reader.buffer, reader.pos) == (expected, expected_pos)


def test_kill_whitespace_and_newline():
    reader = Reader(FakeConsole([]))
    reader.buffer, reader.pos = 'abc  \ndef', 3
    reader.do_cmd(Event('kill-line'))
    assert reader.buffer == 'abcdef'
    reader.do_cmd(Event('yank'))
    assert reader.buffer == 'abc  \ndef'
