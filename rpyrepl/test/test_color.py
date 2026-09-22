import os
import re
import pytest
from rpython.rlib import rutf8
from rpyrepl import color
from rpyrepl.highlight import Highlighter, ColorSpan, Span
from rpyrepl.layout import Layout
from rpyrepl.reader import Reader
from rpyrepl.console import Event
from rpyrepl.test.test_reader import FakeConsole


@pytest.mark.parametrize('env, enabled, tty, expected', [
    ({}, True, True, True), ({}, True, False, False),
    ({'TERM': 'dumb'}, True, True, False),
    ({'FORCE_COLOR': ''}, True, False, True),
    ({'FORCE_COLOR': '0', 'TERM': 'dumb'}, True, False, True),
    ({'NO_COLOR': ''}, True, True, False),
    ({'NO_COLOR': '0', 'FORCE_COLOR': '1'}, True, True, False),
    ({'FORCE_COLOR': '1'}, False, True, False),
    ({'PYTHON_COLORS': '0'}, True, True, True),
    ({'PYROLOG_COLORS': '1'}, True, False, False),
])
def test_color_policy(monkeypatch, env, enabled, tty, expected):
    for key in ['TERM', 'NO_COLOR', 'FORCE_COLOR', 'PYTHON_COLORS', 'PYROLOG_COLORS']:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(os, 'isatty', lambda fd: fd == 17 and tty)
    assert color.can_colorize(17, enabled) == expected


def strip_color(text):
    return re.sub('\x1b\\[[0-9;]*m', '', text)


@pytest.mark.parametrize('width', [1, 2, 8, 20, 80])
def test_styles_preserve_layout_and_cursor(width):
    text = u'\'a\u754ce\u0301\nlong quoted text\' X\x03'.encode('utf-8')
    boundary = text.index(' X')
    spans = [ColorSpan(Span(0, boundary), 'STRING'),
             ColorSpan(Span(boundary + 1, boundary + 2), 'VARIABLE')]
    plain = Layout(text, width, '> ', '... ')
    styled = Layout(text, width, '> ', '... ', spans, True)
    assert [strip_color(row) for row in styled.screen] == plain.screen
    pos = 0
    while True:
        assert styled.pos_to_xy(pos) == plain.pos_to_xy(pos)
        if pos == len(text):
            break
        pos = rutf8.next_codepoint_pos(text, pos)
    for y in range(len(plain.rows)):
        for x in range(width):
            assert styled.xy_to_pos(x, y) == plain.xy_to_pos(x, y)
    # Each physical row can be painted independently, including a viewport
    # starting in the middle of a wrapped/multiline token.
    for row in styled.screen:
        active = False
        for escape in re.findall('\x1b\\[[0-9;]*m', row):
            active = escape != color.RESET
        assert not active


def test_adjacent_spans_reset_and_resume():
    spans = [ColorSpan(Span(0, 1), 'VARIABLE'), ColorSpan(Span(1, 2), 'NUMBER')]
    assert Layout('X1.', 80, '', '', spans, True).screen == [
        color.CYAN + 'X' + color.RESET + color.YELLOW + '1' + color.RESET + '.']


def test_disabled_highlighting_does_not_call_scanner():
    class BrokenHighlighter(Highlighter):
        def gen_colors(self, text):
            raise AssertionError('should not run')
    r = Reader(FakeConsole([]), highlighter=BrokenHighlighter())
    r.buffer = 'X = 1.'
    assert r.calc_screen() == ['X = 1.']


def test_failed_search_style_and_plain_buffer():
    console = FakeConsole([])
    console.can_colorize = True
    r = Reader(console)
    r.buffer = 'draft'
    r.pos = 5
    r.do_cmd(Event('reverse-search'))
    r.do_cmd(Event('text', 'missing'))
    screen = r.calc_screen()
    assert screen[0].startswith(color.BOLD_RED)
    assert r.buffer == 'draft'
    assert r.search.term == 'missing'
