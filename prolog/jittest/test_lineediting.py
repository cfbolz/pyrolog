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

    def spawn(color=False):
        child_env = env.copy()
        child_env.pop('FORCE_COLOR', None)
        child_env.pop('NO_COLOR', None)
        if not color:
            child_env['NO_COLOR'] = '1'
        child = pexpect.spawn(executable, env=child_env, timeout=10)
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


def test_ctrl_arrow_query_editing(console_factory):
    child = console_factory()
    child.expect_exact('>?- ')
    child.send('X = old_value.\x1b[1;5D\x1bdnew_value\r')
    child.expect_exact('X = new_value\r\n')
    child.expect_exact('>?- ')
    child.send('\x1b[A\x01\x1b[1;5C\x0b\x19\r')
    child.expect_exact('X = new_value\r\n')
    child.expect_exact('>?- ')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_predicate_completion(console_factory):
    child = console_factory()
    child.expect_exact('>?- ')
    child.send('assertz(completion_alpha), assertz(completion_alpine).\r')
    child.expect_exact('yes')
    child.expect_exact('>?- ')
    child.send('completion_a\t')
    child.expect_exact('[ not unique ]')
    child.send('\t')
    child.expect_exact('| completion_alpha')
    child.expect_exact('>?- completion_alp')
    child.send('h\t')
    child.expect_exact('>?- completion_alpha')
    child.send('.\r')
    child.expect_exact('yes')
    child.expect_exact('>?- ')
    child.send('atom_cod\t')
    child.expect_exact('>?- atom_codes')
    child.send('(ab, [97,98]).\r')
    child.expect_exact('yes')
    child.expect_exact('>?- ')
    child.send('list:\t')
    child.expect_exact('[ not unique ]')
    child.send('\t')
    child.expect_exact('| ')
    child.expect_exact('>?- list:')
    child.send('reve\t')
    child.expect_exact('>?- list:reverse')
    child.send('([a,b], [b,a]).\r')
    child.expect_exact('yes')
    child.expect_exact('>?- ')
    child.send('reve\t')
    child.expect_exact('>?- reverse')
    child.send('([a,b], [b,a]).\r')
    child.expect_exact('yes')
    child.expect_exact('>?- ')
    child.send('user\t')
    child.expect_exact('>?- user:')
    child.send('completion_alph\t')
    child.expect_exact('>?- user:completion_alpha')
    child.send('.\r')
    child.expect_exact('yes')
    child.expect_exact('>?- ')
    child.send('/* list:\t')
    child.expect_exact('[ no matches ]')
    child.send('\x03')
    child.expect_exact('\x1b[?2004l')
    child.expect_exact('\x1b[?2004h')
    child.expect_exact('>?- ')
    child.send('list:t\t')
    child.expect_exact('[ no matches ]')
    child.send('\x03')
    child.expect_exact('\x1b[?2004l')
    child.expect_exact('\x1b[?2004h')
    child.expect_exact('>?- ')
    child.send('list : t\t')
    child.expect_exact('[ no matches ]')
    child.send('\x03')
    child.expect_exact('\x1b[?2004l')
    child.expect_exact('\x1b[?2004h')
    child.expect_exact('>?- ')
    child.send('list /* module */ : /* predicate */ reve\t')
    child.expect_exact('>?- list /* module */ : /* predicate */ reverse')
    child.send('([a,b], [b,a]).\r')
    child.expect_exact('yes')
    child.expect_exact('>?- ')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_multiline_query_and_persistent_recall(console_factory, tmpdir):
    child = console_factory()
    child.expect_exact('>?- ')
    child.send('X = f(\r')
    child.expect_exact('... ')
    child.send('a,\rb).\r')
    child.expect_exact('X = f(a, b)\r\n')
    child.expect_exact('>?- ')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0
    assert tmpdir.join('history').read_binary() == 'X = f(\r\na,\r\nb).\n'
    child = console_factory()
    child.expect_exact('>?- ')
    child.send('\x10\r')
    child.expect_exact('X = f(a, b)\r\n')
    child.expect_exact('>?- ')
    # A terminated syntax error must not trap the user in continuation input.
    child.send('X = ).\r')
    child.expect_exact('>?- ')
    child.send('X = 1.5\r')
    child.expect_exact('... ')
    child.send('.\r')
    child.expect_exact('X = 1.500000\r\n')
    child.expect_exact('>?- ')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_search_persistent_queries(console_factory, tmpdir):
    tmpdir.join('history').write('X = alpha.\nX = beta.\nX = alphabet.\n')
    child = console_factory()
    child.expect_exact('>?- ')
    child.send('\x12alpha\x12\r')
    child.expect_exact('>?- X = alpha.')
    child.send('\r')
    child.expect_exact('X = alpha\r\n')
    child.expect_exact('>?- ')
    child.send('X = draft.\x12beta\x03\r')
    child.expect_exact('X = draft\r\n')
    child.expect_exact('>?- ')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


def test_bracketed_paste_query(console_factory, tmpdir):
    child = console_factory()
    child.expect_exact('\x1b[?2004h')
    child.expect_exact('>?- ')
    child.send('\x1b[200~X = f(\r\na,\r\nb).\r\n\x1b[201~')
    child.expect_exact('... ')
    # The pasted trailing newline must not execute the complete query.
    assert child.expect_exact(['X = f(a, b)\r\n', pexpect.TIMEOUT], timeout=0.1) == 1
    child.send('\r')
    child.expect_exact('\x1b[?2004l')
    child.expect_exact('X = f(a, b)\r\n')
    child.expect_exact('\x1b[?2004h')
    child.expect_exact('>?- ')
    child.send('\x04')
    child.expect_exact('\x1b[?2004l')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0
    assert tmpdir.join('history').read_binary() == 'X = f(\r\na,\r\nb).\r\n\n'


def test_colored_query_preserves_history_and_results(console_factory, tmpdir):
    child = console_factory(color=True)
    child.expect_exact('\x1b[1;35m>?- \x1b[0m')
    query = "X = f(12, 'ab'). % comment"
    child.send('\x1b[200~' + query + '\x1b[201~')
    child.expect_exact('\x1b[36mX\x1b[0m')
    child.expect_exact('\x1b[33m12\x1b[0m')
    child.expect_exact("\x1b[32m'ab'\x1b[0m")
    child.expect_exact('\x1b[31m% comment\x1b[0m')
    child.send('\r')
    child.expect_exact('\x1b[?2004l')
    child.expect_exact('X = f(12, ab)\r\n')
    assert '\x1b[' not in child.before
    child.expect_exact('\x1b[1;35m>?- \x1b[0m')
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0
    assert tmpdir.join('history').read_binary() == query + '\n'


def test_matching_delimiters_follow_cursor(console_factory):
    child = console_factory(color=True)
    prompt = '\x1b[1;35m>?- \x1b[0m'
    child.expect_exact(prompt)
    child.send('\x1b[200~X = f([a])\x1b[201~')
    child.expect_exact('\x1b[1;4;32m(\x1b[0m[a]\x1b[1;4;32m)\x1b[0m')
    child.send('\x1b[D')
    child.expect_exact('(\x1b[1;4;32m[\x1b[0ma\x1b[1;4;32m]\x1b[0m)')
    child.send('\x1b[C.\r')
    child.expect_exact('X = f([a])\r\n')
    child.expect_exact(prompt)
    child.send('\x1b[200~X = f(]\x1b[201~')
    child.expect_exact('(\x1b[1;4;31m]\x1b[0m')
    child.send('\x03')
    child.expect_exact(prompt)
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


@pytest.mark.parametrize('color', [False, True])
def test_traceback_colors_and_file_links(console_factory, tmpdir, color):
    path = tmpdir.join('trace file #1.pl')
    path.write('outer :- inner, true.\ninner :- throw(oops).\n')
    child = console_factory(color=color)
    prompt = '\x1b[1;35m>?- \x1b[0m' if color else '>?- '
    child.expect_exact(prompt)
    child.send("consult('%s').\r" % str(path))
    child.expect_exact(prompt)
    child.send('outer.\r')
    child.expect_exact('Unhandled exception: oops')
    output = child.before
    if color:
        uri = 'file://' + str(path).replace(' ', '%20').replace('#', '%23')
        assert '\x1b[1;35mERROR:\x1b[0m' in output
        assert '\x1b]8;;' + uri + '\x1b\\' + str(path) + '\x1b]8;;\x1b\\' in output
        assert '\x1b[35muser:outer/0\x1b[0m' in output
    else:
        assert 'ERROR:\r\nTraceback' in output
        assert 'File "%s"' % str(path) in output
        assert '\x1b]8;' not in output
        assert '\x1b[35m' not in output
    child.expect_exact(prompt)
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0


@pytest.mark.parametrize('color', [False, True])
def test_no_more_solutions_color(console_factory, color):
    child = console_factory(color=color)
    prompt = '\x1b[1;35m>?- \x1b[0m' if color else '>?- '
    failure = '\x1b[1;31mNein\x1b[0m\r\n' if color else 'Nein\r\n'
    child.expect_exact(prompt)
    child.send('fail.\r')
    child.expect_exact(failure)
    child.expect_exact(prompt)
    child.send('(X = a; X = b; fail).\r')
    child.expect_exact('X = a\r\n')
    child.send(';\r')
    child.expect_exact('X = b\r\n')
    child.send(';\r')
    child.expect_exact(failure)
    child.expect_exact(prompt)
    child.send('\x04')
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0
