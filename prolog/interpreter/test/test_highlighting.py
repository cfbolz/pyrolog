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
