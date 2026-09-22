"""Tolerant editor highlighting using the parser's existing lexer."""
from rpython.rlib import rutf8
from rpython.rlib.parsing.lexer import LexingDFARunner
from rpython.rlib.parsing.deterministic import LexerError
from rpyrepl.highlight import Highlighter, ColorSpan, Span, delimiter_colors
from prolog.interpreter import parsing


class PrologHighlighter(Highlighter):
    def get_colors(self, text, pos):
        return delimiter_colors(text, pos, self.gen_colors(text))

    def gen_colors(self, text):
        # Reuse the generated matcher and DFA, but retain IGNORE tokens so
        # comments can be styled. Never change the parser's ignore dictionary.
        lexer = parsing.lexer
        runner = LexingDFARunner(lexer.matcher, lexer.automaton, text, {})
        spans = []
        while runner.last_matched_index + 1 < len(text):
            start = runner.last_matched_index + 1
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
                runner.last_matched_index = end - 1
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
