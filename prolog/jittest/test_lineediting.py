"""Real terminal integration for the query editor."""
import os
import pytest
import pexpect


def test_edit_query_and_keep_choice_input_separate():
    executable = os.environ.get('PYROLOG_EXECUTABLE',
        os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'pyrolog-c')))
    if not os.path.isfile(executable):
        if 'PYROLOG_EXECUTABLE' in os.environ:
            pytest.fail('PYROLOG_EXECUTABLE does not exist: ' + executable)
        pytest.skip('build pyrolog-c or set PYROLOG_EXECUTABLE')
    env = os.environ.copy()
    env['TERM'] = 'xterm'
    child = pexpect.spawn(executable, env=env, timeout=10)
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
