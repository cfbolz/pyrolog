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
    assert "Syntax error: 'float_overflow'" in text
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
