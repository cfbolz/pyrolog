import pytest

from prolog.interpreter.lexer import UnicodeLexer
from prolog.interpreter.syntaxerror import SyntaxError
from prolog.interpreter.test.test_parser_diagnostics import position


@pytest.mark.parametrize('source, kind, start, width, expected', [
    ("f('x", 'unclosed_quote', 2, 1, "'"),
    ('"x', 'unclosed_quote', 0, 1, '"'),
    ('a /* comment\n', 'unclosed_comment', 2, 2, '*/'),
])
def test_unclosed_lexical_construct(source, kind, start, width, expected):
    with pytest.raises(SyntaxError) as caught:
        UnicodeLexer().tokenize(source)
    exc = caught.value
    assert exc.kind == kind
    assert (exc.primary.start.i, exc.primary.end.i) == (start, start + width)
    assert exc.secondary.start.i == exc.secondary.end.i == len(source)
    assert exc.expected == expected
    assert exc.found == 'EOF'
    assert exc.incomplete
    assert not hasattr(exc, 'text')


def test_lexer_eof_positions_after_utf8_and_newline():
    with pytest.raises(SyntaxError) as caught:
        UnicodeLexer().tokenize("\xc3\xa9('x\n  ")
    assert position(caught.value.primary.start) == (3, 0, 2)
    assert position(caught.value.secondary.start) == (8, 1, 2)


def test_invalid_character_span():
    with pytest.raises(SyntaxError) as caught:
        UnicodeLexer().tokenize('\xc3\xa9 `.')
    exc = caught.value
    assert exc.kind == 'invalid_token'
    assert position(exc.primary.start) == (3, 0, 2)
    assert position(exc.primary.end) == (4, 0, 3)
    assert not exc.incomplete


def test_invalid_utf8_span():
    with pytest.raises(SyntaxError) as caught:
        UnicodeLexer().tokenize('\xc3\xa9\n\xff')
    exc = caught.value
    assert exc.kind == 'invalid_utf8'
    assert position(exc.primary.start) == (3, 1, 0)
    assert exc.primary.end.i == 4
    assert not exc.incomplete


def test_lexical_errors_use_query_error_conversion():
    from prolog.interpreter import parsing, error
    with pytest.raises(error.CatchableError) as caught:
        parsing.parse_query_term('` .')
    assert caught.value.parse_error.kind == 'invalid_token'
    assert caught.value.term.argument_at(0).name() == 'syntax_error'


@pytest.mark.parametrize('source, kind', [
    ('` .', 'invalid_token'),
    ("'unfinished. ", 'unclosed_quote'),
    ('/* unfinished. ', 'unclosed_comment'),
])
def test_stream_reader_preserves_lexical_diagnostics(tmpdir, source, kind):
    import os
    from rpython.rlib.streamio import fdopen_as_stream
    from prolog.interpreter import error
    from prolog.interpreter.stream import PrologInputStream
    from prolog.builtin.streams import read_till_next_dot
    path = tmpdir.join('source.pl')
    path.write(source)
    stream = PrologInputStream(fdopen_as_stream(os.open(str(path), os.O_RDONLY), 'r'))
    try:
        with pytest.raises(error.CatchableError) as caught:
            read_till_next_dot(stream)
        assert caught.value.parse_error.kind == kind
        assert caught.value.parse_error.primary.start.i == 0
    finally:
        stream.close()


@pytest.mark.parametrize('source, more', [
    ("f('unfinished.", True), ('/* unfinished.', True), ('` .', False),
])
def test_repl_uses_incomplete_flag(source, more):
    from prolog.interpreter.replpolicy import PrologInputPolicy
    assert PrologInputPolicy().more_lines(source) == more
