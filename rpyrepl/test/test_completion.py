import pytest
from rpyrepl.completion import Completer, Completion, common_prefix
from rpyrepl.reader import Reader
from rpyrepl.console import Event
from rpyrepl.test.test_reader import FakeConsole, events


class Words(Completer):
    def __init__(self, words):
        self.words = words

    def complete(self, text, pos):
        start = text.rfind(' ', 0, pos) + 1
        return Completion(start, self.words)


def reader(words, text='', width=40, height=8):
    console = FakeConsole([], width)
    console.height = height
    r = Reader(console, completer=Words(words))
    r.buffer = text
    r.pos = len(text)
    r.prompt = '> '
    return r


def tab(r):
    r.do_cmd(Event('complete'))
    return r.calc_screen()


def test_unique_completion_preserves_suffix():
    r = reader(['member', 'member'], 'call mem(X)')
    r.pos = 8
    tab(r)
    assert r.buffer == 'call member(X)'
    assert r.pos == len('call member')
    assert not r.completion.visible


def test_prefix_message_then_menu_and_filter():
    r = reader(['append', 'apply', 'atom'], 'ap')
    assert tab(r) == ['> app', '[ not unique ]']
    assert r.cxy == (5, 0)
    screen = tab(r)
    assert screen[0].startswith('| ')
    assert 'append' in screen[0] and 'apply' in screen[0]
    assert screen[-1] == '> app'
    assert r.cxy == (5, 1)
    r.do_cmd(Event('text', 'e'))
    assert 'apply' not in ''.join(r.calc_screen())
    tab(r)
    assert r.buffer == 'append'
    r.do_cmd(Event('left'))
    assert r.calc_screen() == ['> append']


def test_complete_but_not_unique_and_no_matches():
    r = reader(['atom', 'atom_codes'], 'at')
    assert tab(r)[-1] == '[ complete but not unique ]'
    r = reader(['atom'], 'xyz')
    assert tab(r) == ['> xyz', '[ no matches ]']
    assert r.buffer == 'xyz'


def test_prefix_stops_at_utf8_boundary():
    words = [u'caf\xe8'.encode('utf-8'), u'caf\xe9'.encode('utf-8')]
    assert common_prefix(words) == 'caf'
    r = reader(words, 'ca')
    tab(r)
    assert r.buffer == 'caf'


def test_paging_and_small_viewports():
    words = ['word%02d' % i for i in range(20)]
    r = reader(words, 'word', width=12, height=4)
    tab(r)
    first = tab(r)
    assert len(first) == 4
    assert first[-1] == '> word'
    assert 'more' in first[-2]
    second = tab(r)
    assert first != second
    seen = set()
    for i in range(20):
        screen = tab(r)
        seen.update(' '.join(screen).split())
        assert len(screen) <= 4
        assert 0 <= r.cxy[1] < len(screen)
    assert set(words).issubset(seen)
    for width in range(1, 5):
        for height in range(1, 4):
            r = reader(words, 'word', width, height)
            tab(r)
            screen = tab(r)
            assert len(screen) <= height
            assert 0 <= r.cxy[1] < len(screen)


def test_menu_does_not_participate_in_vertical_movement():
    r = reader(['append', 'apply'], 'first\napp')
    # This fake completer treats the whole string as its stem; use the last line.
    r.completer = Words(['first\nappend', 'first\napply'])
    tab(r)
    tab(r)
    r.do_cmd(Event('up'))
    assert r.pos <= len('first')
    assert not r.completion.visible


def test_accept_removes_menu_before_finishing():
    console = FakeConsole(events(u'ap', 'complete', 'complete', 'accept'))
    r = Reader(console, completer=Words(['append', 'apply']))
    assert r.readline('> ') == 'app'
    assert console.screens[-1][0] == ['> app']


def test_menu_escapes_controls_and_counts_terminal_columns():
    r = reader([u'a\u754c'.encode('utf-8'), 'a\x1b[31m'], 'a', width=20)
    tab(r)
    screen = tab(r)
    assert '\x1b' not in ''.join(screen)
    assert '^[' in ''.join(screen)


def test_colored_menu_leaves_input_and_coordinates_unchanged():
    r = reader(['append', 'apply'], 'app')
    tab(r)
    plain = tab(r)
    position = r.cxy
    r.console.can_colorize = True
    colored = r.calc_screen()
    assert '\x1b[36m| ' in colored[0]
    assert colored[0].replace('\x1b[36m', '').replace('\x1b[0m', '') == plain[0]
    assert r.buffer == 'app'
    assert r.cxy == position
