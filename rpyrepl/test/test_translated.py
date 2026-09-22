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
    env['NO_COLOR'] = '1'
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
    env['NO_COLOR'] = '1'
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


def test_multiline_editing_and_history(child):
    child.send('(abc\r')
    child.expect_exact('... ')
    child.send('def)\x1b[A\x05!\x1b[B\r')
    child.expect_exact('ACCEPTED:(abc!\r\ndef)\r\n')
    child.expect_exact('edit> ')
    child.send('\x10\r')
    child.expect_exact('ACCEPTED:(abc!\r\ndef)\r\n')
    child.expect_exact('edit> ')
    child.send('(\x1b\r')
    child.expect_exact('ACCEPTED:(\r\n')
    child.expect_exact('edit> ')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_tall_buffer_resize_and_cancel(child):
    child.setwinsize(3, 12)
    child.send('(\r')
    child.expect_exact('... ')
    for i in range(6):
        child.send('line%d\r' % i)
    child.send(')')
    child.setwinsize(5, 18)
    child.send('\x1b[A\x1b[B\r')
    expected = '(\r\n' + ''.join('line%d\r\n' % i for i in range(6)) + ')'
    child.expect_exact('ACCEPTED:' + expected + '\r\n')
    child.expect_exact('edit> ')
    child.send('(\rdiscard\x03')
    child.expect_exact('CANCELLED')
    child.expect_exact('edit> ')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_incremental_history_search(child):
    for entry in ['alpha', 'beta', u'caf\xe9'.encode('utf-8')]:
        child.send(entry + '\r')
        child.expect_exact('ACCEPTED:' + entry + '\r\n')
        child.expect_exact('edit> ')
    child.send('\x12alpha\r')
    child.expect_exact('edit> alpha')
    child.send('\x05!\r')
    child.expect_exact('ACCEPTED:alpha!\r\n')
    child.expect_exact('edit> ')
    child.send('draft\x02\x12' + u'\xe9'.encode('utf-8') + '\x07!\r')
    child.expect_exact('ACCEPTED:draf!t\r\n')
    child.expect_exact('edit> ')
    child.send('\x12' + u'\xe9'.encode('utf-8') + '\r\r')
    child.expect_exact('ACCEPTED:' + u'caf\xe9'.encode('utf-8') + '\r\n')
    child.expect_exact('edit> ')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_bracketed_multiline_paste(child):
    # Incomplete delimiters and a delayed paste body must not become key events.
    child.send('\x1b[200~' + u'(caf\xe9\r\n'.encode('utf-8'))
    assert child.expect_exact(['ACCEPTED:', pexpect.TIMEOUT], timeout=0.1) == 1
    child.send('two)\r\n\x1b[20')
    assert child.expect_exact(['ACCEPTED:', pexpect.TIMEOUT], timeout=0.1) == 1
    child.send('1~')
    child.expect_exact('... ')
    assert child.expect_exact(['ACCEPTED:', pexpect.TIMEOUT], timeout=0.1) == 1
    child.send('\r')
    child.expect_exact('\x1b[?2004l')
    child.expect_exact('ACCEPTED:' + u'(caf\xe9\r\ntwo)\r\n\r\n'.encode('utf-8'))
    child.expect_exact('\x1b[?2004h')
    child.expect_exact('edit> ')
    child.send('\x04')
    child.expect_exact('\x1b[?2004l')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_pasted_controls_are_literal_and_cancel_restores_mode(child):
    child.send('\x1b[200~a\x03\x04\x1b[D\x1b[201~')
    child.expect_exact('a^C^D^[[D')
    child.send('\x03')
    child.expect_exact('\x1b[?2004l')
    child.expect_exact('CANCELLED')
    child.expect_exact('\x1b[?2004h')
    child.expect_exact('edit> ')
    child.send('quit\r')
    child.expect_exact('\x1b[?2004l')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


@pytest.mark.parametrize('no_color, force_color, colored', [
    (None, None, True), ('', '1', False), (None, '', True),
])
def test_color_environment(executable, no_color, force_color, colored):
    env = os.environ.copy()
    env['TERM'] = 'xterm'
    for name, value in [('NO_COLOR', no_color), ('FORCE_COLOR', force_color)]:
        env.pop(name, None)
        if value is not None:
            env[name] = value
    child = pexpect.spawn(executable, env=env, timeout=10)
    try:
        prompt = '\x1b[1;35medit> \x1b[0m' if colored else 'edit> '
        child.expect_exact(prompt)
        if not colored:
            assert '\x1b[1;35m' not in child.before
        child.send('quit\r')
        child.expect_exact('\x1b[?2004l')
        child.expect_exact('ACCEPTED:quit\r\n')
        assert '\x1b[' not in child.before
        child.expect(pexpect.EOF)
        child.close()
        assert child.exitstatus == 0
    finally:
        child.close(force=True)
