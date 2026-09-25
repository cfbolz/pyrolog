import pytest
from rpython.rlib import rutf8
from prolog.interpreter.highlighting import PrologHighlighter
from prolog.interpreter import parsing


def highlighted(text):
    result = []
    end = 0
    for span in PrologHighlighter().gen_colors(text):
        assert end <= span.span.start < span.span.end <= len(text)
        rutf8.check_utf8(text[:span.span.start], False)
        rutf8.check_utf8(text[:span.span.end], False)
        result.append((text[span.span.start:span.span.end], span.tag))
        end = span.span.end
    return result


def test_tokens_comments_and_operators():
    text = 'X = f(12, -1.5e+2, "hello", \'atom\', _), X =.. L. % comment\n/* block */'
    assert highlighted(text) == [
        ('X', 'VARIABLE'), ('12', 'NUMBER'), ('1.5e+2', 'NUMBER'),
        ('"hello"', 'STRING'), ("'atom'", 'STRING'), ('_', 'VARIABLE'),
        ('X', 'VARIABLE'), ('L', 'VARIABLE'), ('% comment', 'COMMENT'),
        ('/* block */', 'COMMENT')]


def test_source_highlighting_obeys_output_fd(monkeypatch):
    from prolog.interpreter.highlighting import highlight_source
    from rpyrepl import color
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.delenv('FORCE_COLOR', raising=False)
    monkeypatch.setenv('TERM', 'xterm')
    monkeypatch.setattr(color.os, 'isatty', lambda fd: fd == 17)
    text = 'f(X, 42).'
    assert highlight_source(text, 17) == (
        'f(' + color.CYAN + 'X' + color.RESET + ', ' +
        color.YELLOW + '42' + color.RESET + ').')
    assert highlight_source(text, 18) == text


@pytest.mark.parametrize('suffix, role', [
    ('"unfinished', 'STRING'), ("'unfinished\ntext", 'STRING'),
    ('/* unfinished\nX = 12.', 'COMMENT'), ('/**', 'COMMENT'),
    ('/*/', 'COMMENT'), ('% comment', 'COMMENT'),
])
def test_unfinished_input(suffix, role):
    assert highlighted('X = 42, ' + suffix) == [
        ('X', 'VARIABLE'), ('42', 'NUMBER'), (suffix, role)]


def test_quotes_inside_comments_and_comments_inside_quotes():
    text = "/* ' */ X = '% /*'. % \"\nY = \"' /*\"."
    assert highlighted(text) == [
        ("/* ' */", 'COMMENT'), ('X', 'VARIABLE'), ("'% /*'", 'STRING'),
        ('% "', 'COMMENT'), ('Y', 'VARIABLE'), ('"\' /*"', 'STRING')]


def test_complete_block_comment_then_unfinished_block():
    assert highlighted('/* one */ X /* two') == [
        ('/* one */', 'COMMENT'), ('X', 'VARIABLE'), ('/* two', 'COMMENT')]


def test_utf8_offsets_and_recovery():
    text = u'X = \'caf\xe9\u754c\', \u754c Y = 42.'.encode('utf-8')
    assert highlighted(text) == [
        ('X', 'VARIABLE'), (u"'caf\xe9\u754c'".encode('utf-8'), 'STRING'),
        ('Y', 'VARIABLE'), ('42', 'NUMBER')]


def test_multiline_token_offsets():
    text = '\n/* a\nb */\n X = "c\nd".'
    spans = PrologHighlighter().gen_colors(text)
    assert [(s.span.start, s.span.end, s.tag) for s in spans] == [
        (1, 10, 'COMMENT'), (12, 13, 'VARIABLE'), (16, 21, 'STRING')]


def test_does_not_change_parser_lexer():
    text = 'X = /* comment */ 12.'
    before = [(t.name, t.source, t.source_pos.i) for t in parsing.lexer.tokenize(text)]
    highlighted(text)
    after = [(t.name, t.source, t.source_pos.i) for t in parsing.lexer.tokenize(text)]
    assert before == after
    assert all(name != 'IGNORE' for name, source, pos in after)


def test_every_prefix_can_be_highlighted():
    text = u'X = f(12.5, "caf\xe9", \'a.b\'). /* comment */\n% tail'.encode('utf-8')
    pos = 0
    while pos < len(text):
        highlighted(text[:pos])
        pos = rutf8.next_codepoint_pos(text, pos)
    highlighted(text)


def delimiter_spans(text, pos):
    spans = PrologHighlighter().get_colors(text, pos)
    end = 0
    result = []
    for color in spans:
        assert end <= color.span.start < color.span.end <= len(text)
        end = color.span.end
        if color.tag in ('MATCHING_DELIMITER', 'MISMATCHED_DELIMITER'):
            result.append((color.span.start, color.tag))
    return result


@pytest.mark.parametrize('text, pos, pair', [
    ('f(a)', 1, [1, 3]), ('f(a)', 2, [1, 3]),
    ('f(a)', 3, [1, 3]), ('f(a)', 4, [1, 3]),
    ('([])', 1, [1, 2]), ('([])', 3, [1, 2]),
    ('([])', 4, [0, 3]), ('[]', 2, [0, 1]), ('{}', 0, [0, 1]),
    ('f([a,\n{b}])', 8, [6, 8]),
    ("f(')', /* ] */ [a])", 1, [1, 18]),
    (u'f(\'\u754c\')'.encode('utf-8'), 8, [1, 7]),
])
def test_matching_delimiters(text, pos, pair):
    assert delimiter_spans(text, pos) == [(i, 'MATCHING_DELIMITER') for i in pair]


@pytest.mark.parametrize('text, pos, bad', [
    (')', 0, 0), (')', 1, 0), ('[)', 2, 1),
    ('([)]', 3, 2), ('([)]', 4, 3), ('f(]', 2, 2),
])
def test_mismatched_delimiters(text, pos, bad):
    assert delimiter_spans(text, pos) == [(bad, 'MISMATCHED_DELIMITER')]


@pytest.mark.parametrize('text, pos', [
    ('(', 1), ('f([', 3), ('f(abc)', 4), ('abc', 2), ('', 0),
    ("'()'", 2), ('"[]"', 2), ('% ()', 4), ('/* () */', 5),
    ("f(')", 4), ('f(/* )', 6), ('f( % )\na', 1),
])
def test_no_delimiter_overlay(text, pos):
    assert delimiter_spans(text, pos) == []


def test_overlay_moves_without_changing_syntax_spans():
    highlighter = PrologHighlighter()
    text = 'X = f([12]).'
    syntax = [(s.span.start, s.span.end, s.tag) for s in highlighter.gen_colors(text)]
    for pos in range(len(text) + 1):
        spans = highlighter.get_colors(text, pos)
        assert [(s.span.start, s.span.end, s.tag) for s in spans
                if s.tag not in ('MATCHING_DELIMITER', 'MISMATCHED_DELIMITER')] == syntax
