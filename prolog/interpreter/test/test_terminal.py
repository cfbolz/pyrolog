import pytest
from prolog.interpreter import translatedmain
from prolog.interpreter.continuation import Engine


def terminal_input(monkeypatch, text):
    monkeypatch.setenv('PYROLOG_HISTORY', '')
    monkeypatch.setattr(translatedmain.rpyrepl, 'make_reader', lambda history=None, policy=None, highlighter=None, completer=None: None)
    chars = iter(text)
    read = translatedmain.os.read

    def read_input(fd, size):
        if fd == 0:
            assert size == 1
            return next(chars, '')
        return read(fd, size)

    output = []
    monkeypatch.setattr(translatedmain.os, 'read', read_input)
    monkeypatch.setattr(translatedmain, 'printmessage', output.append)
    return output


def test_readline_preserves_final_unterminated_line(monkeypatch):
    terminal_input(monkeypatch, 'true.\nfalse.')
    assert translatedmain.readline() == 'true.\n'
    assert translatedmain.readline() == 'false.'
    pytest.raises(translatedmain.EndOfInput, translatedmain.readline)


def test_getch_eof(monkeypatch):
    terminal_input(monkeypatch, '')
    pytest.raises(translatedmain.EndOfInput, translatedmain.getch)


def test_console_recovers_from_float_literal_overflow(monkeypatch):
    output = terminal_input(monkeypatch, 'X is 1.0e999.\ntrue.\nhalt.\n')
    translatedmain.run_console(Engine())
    text = ''.join(output)
    assert "SyntaxError: float overflow" in text
    assert 'yes' in text


@pytest.mark.parametrize('text, expected', [
    ('', 'welcome!'),
    ('\n', 'welcome!'),
    ('true.', 'yes'),
    ('halt.', 'welcome!'),
    ('(X = a; X = b).\n', 'X = a'),
    ('trace.\ntrue.\n', 'Call: (1) true'),
    ('trace.\ntrue.\n\n', 'Exit: (1) true'),
])
def test_console_eof(monkeypatch, text, expected):
    halted = text == 'halt.'
    output = terminal_input(monkeypatch, text)
    engine = Engine()
    translatedmain.run_console(engine)
    text = ''.join(output)
    assert expected in text
    if not halted:
        assert text.endswith('\n')
    assert 'ERROR' not in text
    assert engine.debugger.query_depth == 0
    assert engine.debugger.skip_frame is None


def test_eof_in_startup_file(monkeypatch, tmpdir):
    source = tmpdir.join('startup.pl')
    source.write(':- trace, true.')
    output = terminal_input(monkeypatch, '')
    engine = Engine()
    translatedmain.run_console(engine, str(source))
    text = ''.join(output)
    assert 'Call: (1) true' in text
    assert 'welcome!' not in text
    assert engine.debugger.query_depth == 0


def test_standalone_eof_returns_success(monkeypatch):
    import targetprologstandalone
    terminal_input(monkeypatch, '')
    assert targetprologstandalone.entry_point(['pyrolog']) == 0


def test_query_editor_cancellation_and_eof(monkeypatch):
    output = terminal_input(monkeypatch, '')

    class Reader(object):
        def __init__(self):
            self.calls = 0

        def readline(self, prompt):
            assert prompt == '>?- '
            self.calls += 1
            if self.calls == 1:
                raise translatedmain.rpyrepl.CancelledInput
            if self.calls == 2:
                return 'X = a.'
            raise translatedmain.rpyrepl.EndOfInput

    reader = Reader()
    monkeypatch.setattr(translatedmain.rpyrepl, 'make_reader', lambda history=None, policy=None, highlighter=None, completer=None: reader)
    translatedmain.run_console(Engine())
    assert reader.calls == 3
    assert 'X = a' in ''.join(output)
    assert 'ERROR' not in ''.join(output)


def test_query_history_policy(monkeypatch):
    terminal_input(monkeypatch, '')
    histories = []

    class Reader(object):
        lines = iter(['  ', 'X = a.', 'X = a.', 'X = b.', 'X = a.'])

        def readline(self, prompt):
            try:
                return next(self.lines)
            except StopIteration:
                raise translatedmain.rpyrepl.EndOfInput

    def make_reader(history=None, policy=None, highlighter=None, completer=None):
        histories.append(history)
        return Reader()

    monkeypatch.setattr(translatedmain.rpyrepl, 'make_reader', make_reader)
    translatedmain.run_console(Engine())
    assert histories[0].entries == ['X = a.', 'X = b.', 'X = a.']


def test_history_filename(monkeypatch):
    monkeypatch.delenv('PYROLOG_HISTORY', raising=False)
    monkeypatch.setenv('HOME', '/tmp/pyrolog-history-home')
    assert translatedmain.history_filename() == '/tmp/pyrolog-history-home/.pyrolog_history'
    monkeypatch.setenv('PYROLOG_HISTORY', '/tmp/custom-history')
    assert translatedmain.history_filename() == '/tmp/custom-history'
    monkeypatch.setenv('PYROLOG_HISTORY', '')
    assert translatedmain.history_filename() == ''
    monkeypatch.delenv('PYROLOG_HISTORY')
    monkeypatch.delenv('HOME')
    assert translatedmain.history_filename() == ''


def test_plain_input_does_not_touch_history(monkeypatch, tmpdir):
    terminal_input(monkeypatch, 'X = a.\nhalt.\n')
    path = tmpdir.join('history')
    monkeypatch.setenv('PYROLOG_HISTORY', str(path))
    translatedmain.run_console(Engine())
    assert not path.check()


def test_console_uses_labeled_syntax_diagnostics(monkeypatch):
    from prolog.interpreter.diagnostics import format_syntax_error
    from prolog.interpreter.test.test_parser_diagnostics import diagnostic
    source = 'f(a b).\n'
    output = terminal_input(monkeypatch, source + 'halt.\n')
    translatedmain.run_console(Engine())
    assert format_syntax_error(source, '<stdin>', diagnostic(source)) in ''.join(output)


@pytest.mark.parametrize('tty, term, force, no_color, expected_color', [
    (True, 'xterm', False, False, True),
    (False, 'xterm', False, False, False),
    (True, 'dumb', False, False, False),
    (False, 'dumb', True, False, True),
    (True, 'xterm', True, True, False),
])
def test_syntax_diagnostic_color_policy(monkeypatch, tty, term, force, no_color, expected_color):
    from rpyrepl import color
    from prolog.interpreter.diagnostics import format_syntax_error
    from prolog.interpreter.test.test_parser_diagnostics import diagnostic
    monkeypatch.setenv('TERM', term)
    monkeypatch.delenv('FORCE_COLOR', raising=False)
    monkeypatch.delenv('NO_COLOR', raising=False)
    if force:
        monkeypatch.setenv('FORCE_COLOR', '1')
    if no_color:
        monkeypatch.setenv('NO_COLOR', '1')
    monkeypatch.setattr(color.os, 'isatty', lambda fd: tty and fd == 1)
    source = 'f(a b).\n'
    output = terminal_input(monkeypatch, source + 'halt.\n')
    translatedmain.run_console(Engine())
    expected = format_syntax_error(source, '<stdin>', diagnostic(source), color=expected_color)
    assert expected in ''.join(output)


def test_consult_syntax_diagnostic_color(monkeypatch, tmpdir):
    from rpyrepl.color import filelink
    from prolog.interpreter import parsing, error
    from prolog.interpreter.diagnostics import format_syntax_error
    from prolog.interpreter.test.test_parser_diagnostics import diagnostic
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('FORCE_COLOR', '1')
    source = 'f(a b).'
    path = tmpdir.join('bad file.pl')
    path.write(source)
    output = []
    monkeypatch.setattr(translatedmain, 'printmessage', output.append)
    translatedmain.execute(Engine(), str(path))
    text = ''.join(output)
    link = filelink(str(path))
    assert '[' + link + ':1:5]' in text
    assert '%20' in link
    assert format_syntax_error(source, str(path), diagnostic(source), color=True) in text.replace(link, str(path))
    with pytest.raises(error.PrologParseError) as caught:
        parsing.parse_file(source)
    assert '\x1b[' not in caught.value.message


def test_syntax_filename_link_uses_output_fd(monkeypatch):
    from prolog.interpreter import parsing, error
    from rpyrepl import color
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.delenv('FORCE_COLOR', raising=False)
    monkeypatch.setenv('TERM', 'xterm')
    monkeypatch.setattr(color.os, 'isatty', lambda fd: fd == 17)
    with pytest.raises(error.PrologParseError) as caught:
        parsing.parse_file('f(a b).', file_name='example.pl')
    exc = caught.value
    assert color.filelink('example.pl', 17) in exc.format_message(17)
    assert '\x1b]8;;' in exc.format_message(17)
    assert exc.format_message(18) == exc.message
    assert '\x1b' not in exc.message


def test_console_projection_preserves_redo_and_repeat(monkeypatch):
    output = terminal_input(monkeypatch,
        'when(nonvar(X),Y=done), (true;X=a).\np\n;\nhalt.\n')
    translatedmain.run_console(Engine(load_system=True))
    text = ''.join(output)
    assert text.count('coroutines:when(nonvar(X), user:(Y=done))') == 2
    assert 'X = a\nY = done' in text
    assert 'ERROR' not in text


def test_console_hook_runs_once_and_restores_source(monkeypatch, capfd):
    from prolog.interpreter.parsing import get_engine
    engine = get_engine('''
        :- module(projected, []).
        attribute_goals(X, [constraint(X,Value)], []) :-
            write(projecting), nl,
            get_attr(X, projected, Value), del_attr(X, projected).
        :- module(user).
    ''', load_system=True)
    output = terminal_input(monkeypatch,
        'put_attr(X,projected,Y), (true;get_attr(X,projected,Y),Y=kept).\n'
        'p\n;\n\nhalt.\n')
    translatedmain.run_console(engine)
    text = ''.join(output)
    assert text.count('constraint(X, Y)') == 2
    assert 'Y = kept\nconstraint(X, kept)' in text
    assert 'ERROR' not in text
    out, err = capfd.readouterr()
    assert out == 'projecting\nprojecting\n'


def test_deep_answer_through_repl_continuation():
    from prolog.interpreter.term import Callable
    value = Callable.build('a')
    for i in range(3000):
        value = Callable.build('f', [value])
    engine = Engine()
    output = []
    display = translatedmain.ContinueContinuation(engine, {'X': value}, output.append)
    engine.run_query_in_current(Callable.build('true'), display)
    assert ''.join(output) == 'yes\nX = ' + 'f(' * 20 + '...' + ')' * 20 + '\n\n'
