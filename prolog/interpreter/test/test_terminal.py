import py
from prolog.interpreter import translatedmain
from prolog.interpreter.continuation import Engine


def terminal_input(monkeypatch, text):
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
    py.test.raises(translatedmain.EndOfInput, translatedmain.readline)


def test_getch_eof(monkeypatch):
    terminal_input(monkeypatch, '')
    py.test.raises(translatedmain.EndOfInput, translatedmain.getch)


@py.test.mark.parametrize('text, expected', [
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
