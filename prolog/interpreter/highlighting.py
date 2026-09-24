"""Tolerant editor highlighting using the parser's existing lexer."""
from rpython.rlib import rutf8
from rpython.rlib.parsing.deterministic import LexerError
from rpyrepl.highlight import Highlighter, ColorSpan, Span, delimiter_colors
from prolog.interpreter import parsing


class PrologHighlighter(Highlighter):
    def get_colors(self, text, pos):
        return delimiter_colors(text, pos, self.gen_colors(text))

    def gen_colors(self, text):
        # Use the same code-point boundaries and token classes as the parser.
        runner = parsing.lexer.get_runner(text, ignore_layout=False)
        spans = []
        while runner.pos < len(text):
            start = runner.pos
            assert start >= 0
            # An unfinished block comment otherwise lexes as '/' and '*'.
            if (text[start] == '/' and start + 1 < len(text) and
                    text[start + 1] == '*' and text.find('*/', start + 2) < 0):
                spans.append(ColorSpan(Span(start, len(text)), 'COMMENT'))
                break
            try:
                token = runner.find_next_token()
            except LexerError:
                if text[start] in ("'", '"'):
                    spans.append(ColorSpan(Span(start, len(text)), 'STRING'))
                    break
                # Leave an invalid character plain and resume after it. Skip
                # a whole UTF-8 code point, keeping every span on a boundary.
                end = rutf8.next_codepoint_pos(text, start)
                runner.pos = end
                continue
            except StopIteration:
                break
            tag = ''
            if token.name == 'VAR':
                tag = 'VARIABLE'
            elif token.name in ('NUMBER', 'FLOAT'):
                tag = 'NUMBER'
            elif token.name == 'STRING' or (
                    token.name == 'ATOM' and token.source.startswith("'")):
                tag = 'STRING'
            elif token.name == 'IGNORE' and (token.source.startswith('%') or
                                             token.source.startswith('/*')):
                tag = 'COMMENT'
            if tag:
                spans.append(ColorSpan(Span(start, start + len(token.source)), tag))
        return spans
