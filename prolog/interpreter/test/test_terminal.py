import pytest
from prolog.interpreter import translatedmain
from prolog.interpreter.continuation import Engine


def terminal_input(monkeypatch, text):
    monkeypatch.setattr(translatedmain.rpyrepl, 'make_reader', lambda history=None: None)
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
            assert prompt == u'>?- '
            self.calls += 1
            if self.calls == 1:
                raise translatedmain.rpyrepl.CancelledInput
            if self.calls == 2:
                return u'X = a.'
            raise translatedmain.rpyrepl.EndOfInput

    reader = Reader()
    monkeypatch.setattr(translatedmain.rpyrepl, 'make_reader', lambda history=None: reader)
    translatedmain.run_console(Engine())
    assert reader.calls == 3
    assert 'X = a' in ''.join(output)
    assert 'ERROR' not in ''.join(output)


def test_query_history_policy(monkeypatch):
    terminal_input(monkeypatch, '')
    histories = []

    class Reader(object):
        lines = iter([u'  ', u'X = a.', u'X = a.', u'X = b.', u'X = a.'])

        def readline(self, prompt):
            try:
                return next(self.lines)
            except StopIteration:
                raise translatedmain.rpyrepl.EndOfInput

    def make_reader(history=None):
        histories.append(history)
        return Reader()

    monkeypatch.setattr(translatedmain.rpyrepl, 'make_reader', make_reader)
    translatedmain.run_console(Engine())
    assert histories[0].limit == 1000
    assert histories[0].entries == [u'X = a.', u'X = b.', u'X = a.']
