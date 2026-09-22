"""Real terminal integration for the query editor."""
import os
import pytest
import pexpect


@pytest.fixture
def executable():
    executable = os.environ.get('PYROLOG_EXECUTABLE',
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'pyrolog-c')))
    if not os.path.isfile(executable):
        if 'PYROLOG_EXECUTABLE' in os.environ:
            pytest.fail('PYROLOG_EXECUTABLE does not exist: ' + executable)
        pytest.skip('build pyrolog-c or set PYROLOG_EXECUTABLE')
    return executable


@pytest.fixture
def console_factory(request, tmpdir, executable):
    env = os.environ.copy()
    env['TERM'] = 'xterm'
    env['PYROLOG_HISTORY'] = str(tmpdir.join('history'))

    def spawn():
        child = pexpect.spawn(executable, env=env, timeout=10)
        request.addfinalizer(lambda: child.close(force=True))
        return child

    return spawn


def test_edit_query_and_keep_choice_input_separate(console_factory):
    child = console_factory()
    try:
        child.expect_exact('>?- ')
        child.send('discard\x03')
        child.expect_exact('>?- ')
        child.send('X = ab.\x1b[D\x7f\r')
        child.expect_exact('X = a\r\n')
        child.expect_exact('>?- ')
        # Recall an accepted query, edit it, then navigate across both entries.
        child.send('\x1b[A\x1b[D\x7fb\r')
        child.expect_exact('X = b\r\n')
        child.expect_exact('>?- ')
        child.send('\x10\x10\x0e\r')
        child.expect_exact('X = b\r\n')
        child.expect_exact('>?- ')
        # Consecutive duplicate queries do not occupy another history entry.
        child.send('\x1b[A\x1b[A\r')
        child.expect_exact('X = a\r\n')
        child.expect_exact('>?- ')
        child.send('(X = a; X = b).\r')
        child.expect_exact('X = a\r\n')
        child.send(';\n')
        child.expect_exact('X = b\r\n')
        child.expect_exact('>?- ')
        child.send('\x04')
        child.expect(pexpect.EOF)
        child.close()
        assert child.exitstatus == 0
    finally:
        child.close(force=True)


def test_persistent_history_across_concurrent_sessions(console_factory, tmpdir):
    first, second = console_factory(), console_factory()
    for child in [first, second]:
        child.expect_exact('>?- ')
    first.send('X = a.\r')
    first.expect_exact('X = a\r\n')
    first.expect_exact('>?- ')
    # Entries are already on disk while both sessions are still running.
    assert tmpdir.join('history').read() == 'X = a.\n'
    second.send('X = b.\r')
    second.expect_exact('X = b\r\n')
    second.expect_exact('>?- ')
    for child in [second, first]:
        child.send('\x04')
        child.expect(pexpect.EOF)
        child.close()
        assert child.exitstatus == 0
    assert tmpdir.join('history').read() == 'X = a.\nX = b.\n'

    third = console_factory()
    third.expect_exact('>?- ')
    third.send('\x1b[A\r')
    third.expect_exact('X = b\r\n')
    third.expect_exact('>?- ')
    # Recalling the newest query does not append a duplicate.
    assert tmpdir.join('history').read() == 'X = a.\nX = b.\n'
    third.send('\x1b[A\x1b[A\r')
    third.expect_exact('X = a\r\n')
    third.expect_exact('>?- ')
    third.send('\x04')
    third.expect(pexpect.EOF)


def test_bad_history_path_keeps_editor_usable(console_factory, tmpdir):
    # A directory cannot serve as a history file, even when tests run as root.
    tmpdir.mkdir('history')
    child = console_factory()
    child.expect_exact('Warning: could not read query history')
    child.expect_exact('>?- ')
    child.send('X = a.\r')
    child.expect_exact('X = a\r\n')
    child.expect_exact('>?- ')
    child.send('\x1b[A\r')
    child.expect_exact('X = a\r\n')
    child.expect_exact('>?- ')
    child.send('\x04')
    child.expect(pexpect.EOF)
