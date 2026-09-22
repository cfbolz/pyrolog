import errno
import os
import pytest
from rpyrepl.history import History


def test_roundtrip_and_incremental_save(tmpdir):
    path = str(tmpdir.join('history'))
    history = History()
    entries = ['first', u'caf\xe9\n\u754c'.encode('utf-8'), 'third']
    for entry in entries:
        history.append(entry)
        history.save(path)
        history.save(path)
    assert tmpdir.join('history').read_binary() == 'first\ncaf\xc3\xa9\r\n\xe7\x95\x8c\nthird\n'
    assert os.stat(path).st_mode & 0777 == 0600
    loaded = History()
    loaded.load(path)
    assert loaded.entries == entries
    loaded.save(path)
    loaded.append('fourth')
    loaded.save(path)
    again = History()
    again.load(path)
    assert again.entries == entries + ['fourth']


def test_missing_and_empty_history(tmpdir):
    path = str(tmpdir.join('history'))
    history = History()
    with pytest.raises(OSError) as exc:
        history.load(path)
    assert exc.value.errno == errno.ENOENT
    history.save(path)
    assert not os.path.exists(path)
    history.append('first')
    history.save(path)
    assert tmpdir.join('history').read() == 'first\n'


def test_bad_entries_and_missing_final_newline(tmpdir):
    path = tmpdir.join('history')
    path.write_binary('good\n\xff\n\ned\xed\xa0\x80\r\nbad\nlast')
    history = History()
    history.load(str(path))
    assert history.entries == ['good', 'last']
    history.append('next')
    history.save(str(path))
    again = History()
    again.load(str(path))
    assert again.entries == ['good', 'last', 'next']


def test_concurrent_sessions_do_not_overwrite(tmpdir):
    path = tmpdir.join('history')
    path.write('shared\n')
    first, second = History(), History()
    first.load(str(path))
    second.load(str(path))
    first.append('one')
    second.append('two')
    first.save(str(path))
    second.save(str(path))
    first.append('three')
    first.save(str(path))
    assert path.read() == 'shared\none\ntwo\nthree\n'
    assert second.entries == ['shared', 'two']


def test_write_failure_keeps_unsaved_entries(tmpdir, monkeypatch):
    history = History()
    history.append('keep me')
    path = str(tmpdir.join('history'))
    write = os.write

    def fail(fd, data):
        raise OSError(errno.EACCES, 'test failure')

    monkeypatch.setattr(os, 'write', fail)
    with pytest.raises(OSError):
        history.save(path)
    assert history.entries == ['keep me']
    assert history.saved_count == 0
    monkeypatch.setattr(os, 'write', write)
    history.save(path)
    assert tmpdir.join('history').read() == 'keep me\n'


def test_interrupted_and_short_writes(tmpdir, monkeypatch):
    history = History()
    history.append('some text')
    calls = []
    write = os.write

    def short_write(fd, data):
        calls.append(data)
        if len(calls) == 1:
            raise OSError(errno.EINTR, 'interrupted')
        return write(fd, data[:2])

    monkeypatch.setattr(os, 'write', short_write)
    history.save(str(tmpdir.join('history')))
    assert tmpdir.join('history').read() == 'some text\n'


@pytest.mark.parametrize('prefix', ['', 'old'])
@pytest.mark.parametrize('zero_write', [False, True])
def test_retry_after_partial_write(tmpdir, monkeypatch, prefix, zero_write):
    path = tmpdir.join('history')
    path.write_binary(prefix)
    history = History()
    history.load(str(path))
    entry = u'member(X,\n[caf\xe9,b]).'.encode('utf-8')
    history.append(entry)
    write = os.write
    calls = []

    def partial_then_fail(fd, data):
        calls.append(data)
        if len(calls) == 1:
            # Include a split UTF-8 code point in the written prefix.
            return write(fd, data[:data.index('\xc3') + 1])
        if zero_write:
            return 0
        raise OSError(errno.ENOSPC, 'disk full')

    monkeypatch.setattr(os, 'write', partial_then_fail)
    with pytest.raises(OSError):
        history.save(str(path))
    with pytest.raises(OSError):
        history.save(str(path))
    history.append('next')
    monkeypatch.setattr(os, 'write', write)
    history.save(str(path))
    history.save(str(path))
    expected = ([prefix] if prefix else []) + [entry, 'next']
    loaded = History()
    loaded.load(str(path))
    assert loaded.entries == expected
    assert history.saved_count == len(expected)
