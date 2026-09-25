"""Query termination for the editor, using Pyrolog's lexical conventions."""
from rpyrepl.policy import InputPolicy
from prolog.interpreter import parsing
from prolog.interpreter.syntaxerror import SyntaxError


class PrologInputPolicy(InputPolicy):
    def more_lines(self, text):
        try:
            tokens = parsing.lexer.tokenize(text)
        except SyntaxError as exc:
            return exc.incomplete
        # Tokenization distinguishes full stops from floats, quotes and =...
        # Once a full stop is present, syntax errors must reach the parser.
        return bool(tokens) and tokens[-1].name != '.'
