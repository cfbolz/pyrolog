"""Query termination for the editor, using Pyrolog's lexical conventions."""
from rpyrepl.policy import InputPolicy
from prolog.interpreter import parsing
from rpython.rlib.parsing.deterministic import LexerError


class PrologInputPolicy(InputPolicy):
    def more_lines(self, text):
        # The lexer cannot tokenize an unfinished quote or block comment.
        # Match its current rules: quoted tokens do not recognize escapes.
        pos = 0
        while pos < len(text):
            char = text[pos]
            if char == "'" or char == '"':
                end = text.find(char, pos + 1)
                if end < 0:
                    return True
                pos = end + 1
            elif char == '%':
                end = text.find('\n', pos)
                if end < 0:
                    break
                pos = end + 1
            elif char == '/' and pos + 1 < len(text) and text[pos + 1] == '*':
                end = text.find('*/', pos + 2)
                if end < 0:
                    return True
                pos = end + 2
            else:
                pos += 1
        try:
            tokens = parsing.lexer.tokenize(text)
        except LexerError:
            # Let the normal parser report invalid input immediately.
            return False
        # Tokenization distinguishes full stops from floats, quotes and =...
        # Once a full stop is present, syntax errors must reach the parser.
        return bool(tokens) and tokens[-1].name != '.'
