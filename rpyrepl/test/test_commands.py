import pytest
from rpyrepl.console import Event
from rpyrepl.reader import Reader
from rpyrepl.test.test_reader import FakeConsole, events


def set_buffer(reader, marked):
    before, after = marked.split(u'|')
    reader.buffer = (before + after).encode('utf-8')
    reader.pos = len(before.encode('utf-8'))


def assert_buffer(reader, marked):
    before, after = marked.split(u'|')
    assert reader.buffer[:reader.pos] == before.encode('utf-8')
    assert reader.buffer[reader.pos:] == after.encode('utf-8')


@pytest.mark.parametrize('before, command, after', [
    (u'|one_two, three', 'forward-word', u'one_two|, three'),
    (u'one_two|, three', 'forward-word', u'one_two, three|'),
    (u'one_two, |three', 'backward-word', u'|one_two, three'),
    (u'one_two, three|', 'backward-word', u'one_two, |three'),
    (u'on|e', 'forward-word', u'one|'),
    (u'on|e', 'backward-word', u'|one'),
    (u'|caf\xe9 \u754c\u754c', 'forward-word', u'caf\xe9| \u754c\u754c'),
    (u'caf\xe9 \u754c\u754c|', 'backward-word', u'caf\xe9 |\u754c\u754c'),
    (u'|cafe\u0301', 'forward-word', u'cafe\u0301|'),
    (u'cafe\u0301|', 'backward-word', u'|cafe\u0301'),
    (u'one\U0001f600|two', 'backward-word', u'|one\U0001f600two'),
    (u'one|\U0001f600two', 'forward-word', u'one\U0001f600two|'),
    (u'|  ,.', 'forward-word', u'  ,.|'),
    (u'  ,.|', 'backward-word', u'|  ,.'),
    (u'|one', 'backward-word', u'|one'),
    (u'one|', 'forward-word', u'one|'),
    (u'|', 'forward-word', u'|'),
    (u'|', 'backward-word', u'|'),
])
def test_word_movement(before, command, after):
    reader = Reader(FakeConsole([]))
    set_buffer(reader, before)
    reader.do_cmd(Event(command))
    assert_buffer(reader, after)


@pytest.mark.parametrize('before, command, after, killed', [
    (u'one two|', 'backward-kill-word', u'one |', u'two'),
    (u'one, |two', 'backward-kill-word', u'|two', u'one, '),
    (u'|one, two', 'kill-word', u'|, two', u'one'),
    (u'one|, two', 'kill-word', u'one|', u', two'),
    (u'one |two', 'unix-line-discard', u'|two', u'one '),
    (u'one |two', 'kill-line', u'one |', u'two'),
    (u'caf\xe9 \u754c\u754c|', 'backward-kill-word', u'caf\xe9 |', u'\u754c\u754c'),
    (u'|cafe\u0301', 'kill-word', u'|', u'cafe\u0301'),
])
def test_deletion_and_yank(before, command, after, killed):
    reader = Reader(FakeConsole([]))
    set_buffer(reader, before)
    original = reader.buffer
    reader.do_cmd(Event(command))
    assert_buffer(reader, after)
    assert reader.kill_buffer == killed.encode('utf-8')
    reader.do_cmd(Event('yank'))
    assert reader.buffer == original


@pytest.mark.parametrize('command', ['backward-kill-word', 'kill-word',
                                    'unix-line-discard', 'kill-line'])
def test_empty_deletions_preserve_yank(command):
    reader = Reader(FakeConsole([]))
    reader.kill_buffer = 'saved'
    reader.do_cmd(Event(command))
    reader.do_cmd(Event('yank'))
    assert reader.buffer == 'saved'


@pytest.mark.parametrize('keys', [
    ['backward-kill-word', 'backward-kill-word'],
    ['home', 'kill-word', 'kill-word'],
    ['backward-word', 'kill-line', 'unix-line-discard'],
])
def test_consecutive_kills_keep_text_order(keys):
    console = FakeConsole(events(u'one two', *keys) + events('yank', 'accept'))
    assert Reader(console).readline() == 'one two'


def test_movement_breaks_kill_accumulation():
    console = FakeConsole(events(u'one two', 'backward-kill-word', 'left',
                                 'backward-kill-word', 'yank', 'accept'))
    assert Reader(console).readline() == 'one '


def test_yank_survives_readline_but_kill_accumulation_does_not():
    console = FakeConsole(events(u'old', 'unix-line-discard', 'accept',
                                 'yank', 'accept', u'new', 'unix-line-discard',
                                 'yank', 'accept'))
    reader = Reader(console)
    assert reader.readline() == ''
    assert reader.readline() == 'old'
    assert reader.readline() == 'new'


def test_kill_after_scrolling_utf8():
    console = FakeConsole(events(u'\u754c\u754c caf\xe9', 'backward-kill-word',
                                 'unix-line-discard', 'yank', 'accept'), width=8)
    assert Reader(console).readline() == u'\u754c\u754c caf\xe9'.encode('utf-8')
