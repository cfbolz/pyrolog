"""Query termination for the editor, using Pyrolog's lexical conventions."""
from rpyrepl.policy import InputPolicy
from prolog.interpreter import parsing
from rpython.rlib.parsing.deterministic import LexerError


class PrologInputPolicy(InputPolicy):
    def more_lines(self, text):
        try:
            tokens = parsing.lexer.tokenize(text)
        except LexerError as exc:
            start = exc.source_pos.i
            assert start >= 0
            # The shared lexer reports unterminated tokens at their opening.
            if start < len(text) and text[start] in "'\"":
                return True
            if text[start:start + 2] == '/*':
                return True
            # Let the normal parser report other invalid input immediately.
            return False
        # Tokenization distinguishes full stops from floats, quotes and =...
        # Once a full stop is present, syntax errors must reach the parser.
        return bool(tokens) and tokens[-1].name != '.'
