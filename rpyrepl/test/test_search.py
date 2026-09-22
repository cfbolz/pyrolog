import pytest
from rpyrepl.console import Event
from rpyrepl.history import History
from rpyrepl.reader import Reader
from rpyrepl.test.test_reader import FakeConsole, events


def reader(entries, draft=''):
    history = History()
    for entry in entries:
        history.append(entry)
    result = Reader(FakeConsole([]), history)
    result.history_index = len(entries)
    result.buffer = draft
    result.pos = len(draft)
    return result


def command(r, name, text=''):
    r.do_cmd(Event(name, text))


def test_reverse_occurrences_and_direction():
    r = reader(['alpha', 'alpha beta alpha', 'other'])
    command(r, 'reverse-search')
    command(r, 'text', 'alpha')
    assert (r.history_index, r.pos) == (1, 11)
    command(r, 'reverse-search')
    assert (r.history_index, r.pos) == (1, 0)
    command(r, 'reverse-search')
    assert (r.history_index, r.pos) == (0, 0)
    command(r, 'reverse-search')
    assert r.search.failed
    assert r.buffer == 'alpha'
    command(r, 'forward-search')
    assert (r.history_index, r.pos) == (1, 0)
    assert not r.search.failed


def test_utf8_failure_and_backspace():
    r = reader([u'caf\xe9'.encode('utf-8')])
    command(r, 'reverse-search')
    command(r, 'text', u'\xe9'.encode('utf-8'))
    assert r.pos == 3
    command(r, 'text', u'\u754c'.encode('utf-8'))
    assert r.search.failed
    assert 'failed' in r.search.prompt()
    command(r, 'backspace')
    assert r.search.term == u'\xe9'.encode('utf-8')
    assert not r.search.failed
    command(r, 'backspace')
    assert r.search.term == ''
    assert r.buffer == ''


@pytest.mark.parametrize('cancel', ['cancel', 'abort-search'])
def test_cancel_restores_draft_and_cursor(cancel):
    r = reader(['old'], 'draft')
    r.pos = 2
    original = (r.buffer, r.pos, r.history_index, r.draft, r.draft_pos)
    command(r, 'reverse-search')
    command(r, 'text', 'old')
    command(r, cancel)
    assert r.search is None
    assert (r.buffer, r.pos, r.history_index, r.draft, r.draft_pos) == original


def test_accept_then_history_restores_draft():
    r = reader(['old'], 'draft')
    r.pos = 2
    command(r, 'reverse-search')
    command(r, 'text', 'old')
    command(r, 'accept')
    assert r.search is None and not r.finished
    assert r.buffer == 'old'
    command(r, 'next-history')
    assert (r.buffer, r.pos) == ('draft', 2)
    assert r.history.entries == ['old']


def test_search_edited_history_and_cancel():
    r = reader(['old', 'new'], 'draft')
    command(r, 'previous-history')
    command(r, 'text', '!')
    command(r, 'reverse-search')
    command(r, 'text', 'old')
    command(r, 'abort-search')
    assert (r.buffer, r.pos, r.history_index) == ('new!', 4, 1)
    command(r, 'next-history')
    assert r.buffer == 'draft'
    assert r.history.entries == ['old', 'new']


def test_forward_search_multiline_and_edit_key():
    r = reader(['old', '(one\ntwo)'])
    command(r, 'previous-history')
    command(r, 'previous-history')
    command(r, 'forward-search')
    command(r, 'text', 'two')
    assert (r.buffer, r.pos) == ('(one\ntwo)', 5)
    command(r, 'right')
    assert r.search is None and r.pos == 6


@pytest.mark.parametrize('history', [None, History()])
def test_no_history_and_search_current_input(history):
    r = Reader(FakeConsole(events(u'abc', 'reverse-search', u'b',
                                 'accept', 'accept')), history)
    assert r.readline() == 'abc'
    assert r.pos == 1


def test_empty_search_repeat_and_escape():
    r = reader(['one', 'two'])
    command(r, 'reverse-search')
    command(r, 'reverse-search')
    assert r.buffer == 'two'
    command(r, 'reverse-search')
    assert r.buffer == 'one'
    command(r, 'escape')
    assert r.search is None and not r.finished


def test_readline_search_reset():
    r = reader(['old'])
    r.console.events = events('reverse-search', u'old', 'accept', 'accept',
                              u'new', 'accept')
    assert r.readline() == 'old'
    assert r.readline() == 'new'
