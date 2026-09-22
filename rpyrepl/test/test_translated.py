"""PTY tests for the independent translated target (RPYREPL_EXECUTABLE)."""
import os
import subprocess
import pytest
import pexpect


@pytest.fixture
def executable():
    path = os.environ.get('RPYREPL_EXECUTABLE')
    if not path:
        pytest.skip('set RPYREPL_EXECUTABLE to the translated test target')
    assert os.path.isfile(path)
    return path


@pytest.fixture
def child(request, executable):
    env = os.environ.copy()
    env['TERM'] = 'xterm'
    child = pexpect.spawn(executable, env=env, timeout=10, dimensions=(24, 20))
    request.addfinalizer(lambda: child.close(force=True))
    child.expect_exact('edit> ')
    return child


def test_edit_cancel_and_eof(child):
    child.send('abc\x1b[D\x7fX\r')
    child.expect_exact('ACCEPTED:aXc\r\n')
    child.expect_exact('edit> ')
    child.send('discard\x03')
    child.expect_exact('CANCELLED')
    child.expect_exact('edit> ')
    child.send('\x04')
    child.expect_exact('EOF')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_utf8_and_long_input(child):
    text = u'abcdefghijklmnop\xe9\u754c'.encode('utf-8')
    child.send(text + '\x7f!\r')
    child.expect_exact('ACCEPTED:' + u'abcdefghijklmnop\xe9!'.encode('utf-8'))
    child.expect_exact('edit> ')
    child.send('quit\r')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_pipe_fallback(executable):
    process = subprocess.Popen([executable], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate('')
    assert process.returncode == 0
    assert out == 'plain input\n'
    assert err == ''


def test_history_and_draft(child):
    child.send('first\r')
    child.expect_exact('ACCEPTED:first\r\n')
    child.expect_exact('edit> ')
    child.send('draft\x1b[D\x1b[A\x1b[B!\r')
    child.expect_exact('ACCEPTED:draf!t\r\n')
    child.expect_exact('edit> ')
    child.send('\x10\x10\r')
    child.expect_exact('ACCEPTED:first\r\n')
    child.expect_exact('edit> ')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_utf8_navigation_and_history(child):
    child.send(u'\xe9\u754c\U0001f600'.encode('utf-8') + '\x1b[D\x7f\r')
    child.expect_exact('ACCEPTED:' + u'\xe9\U0001f600'.encode('utf-8') + '\r\n')
    child.expect_exact('edit> ')
    child.send('\x1b[A\x01\x1b[C\x1b[3~!\r')
    child.expect_exact('ACCEPTED:' + u'\xe9!'.encode('utf-8') + '\r\n')
    child.expect_exact('edit> ')
    child.send(u'a\xe9z'.encode('utf-8') + '\x1b[D\x1b[A\x1b[B!\r')
    child.expect_exact('ACCEPTED:' + u'a\xe9!z'.encode('utf-8') + '\r\n')
    child.expect_exact('edit> ')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_persistent_utf8_history(executable, tmpdir):
    env = os.environ.copy()
    env['TERM'] = 'xterm'
    path = str(tmpdir.join('history'))
    text = u'caf\xe9\u754c\U0001f600'.encode('utf-8')
    for keys in [text + '\r', '\x1b[A\r']:
        child = pexpect.spawn(executable, [path], env=env, timeout=10)
        try:
            child.expect_exact('edit> ')
            child.send(keys)
            child.expect_exact('ACCEPTED:' + text + '\r\n')
            child.expect_exact('edit> ')
            child.send('\x04')
            child.expect(pexpect.EOF)
            child.close()
            assert child.exitstatus == 0
        finally:
            child.close(force=True)


@pytest.mark.parametrize('keys, expected', [
    ('one_two three\x1b[1;5D\x1bdnew\r', 'one_two new'),
    ('one two\x1bOd\x1bOc!\r', 'one two!'),
    ('one two\x1bb\x1bdthree\x1bb\x1bf!\r', 'one three!'),
    ('one two\x1b\x7fX\x17Y\r', 'one Y'),
    ('one two\x1bb\x0b\x15\x19\r', 'one two'),
    (u'caf\xe9 \u754c\u754c'.encode('utf-8') + '\x1b[1;5D\x1bd\x19\r',
     u'caf\xe9 \u754c\u754c'.encode('utf-8')),
])
def test_word_commands(child, keys, expected):
    child.send(keys)
    child.expect_exact('ACCEPTED:' + expected + '\r\n')
    child.expect_exact('edit> ')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0
