"""Code-point aware Prolog lexer with byte offsets into the original source."""
from rpython.rlib import rutf8, rstring
from rpython.rlib.parsing.lexer import Token, SourcePos
from rpython.rlib.parsing.deterministic import LexerError
from prolog.interpreter import utf8


# Retain the existing ASCII operator tokenization, including :/ predicate indicators.
GRAPHIC_TOKENS = sorted([
    '-->', ':-', '?-', '->', '\\+', '~', '<', '=', '=..', '=@=', '=:=',
    '=<', '==', '=\\=', '>', '?=', '>=', '@<', '@=<', '@>', '@>=',
    '\\=', '\\==', ':', '+', '-', '/\\', '\\/', '?', '\\', '*', '/',
    '//', '<<', '>>', '**', '^'], key=len, reverse=True)


class IncompleteTokenError(LexerError):
    """A quoted token or block comment needs more input."""


class UnicodeLexer(object):
    def get_runner(self, text, eof=False, ignore_layout=True):
        return UnicodeRunner(text, eof, ignore_layout)

    def tokenize(self, text, eof=False):
        runner = self.get_runner(text, eof)
        tokens = []
        while True:
            try:
                tokens.append(runner.find_next_token())
            except StopIteration:
                return tokens


class UnicodeRunner(object):
    def __init__(self, text, eof=False, ignore_layout=True):
        self.text = text
        self.pos = 0
        self.lineno = 0
        self.columnno = 0
        self.eof = eof
        self.ignore_layout = ignore_layout
        try:
            rutf8.check_utf8(text, allow_surrogates=False)
        except rutf8.CheckError as exc:
            # check_utf8 reports the start of the first invalid sequence.
            while self.pos < exc.pos:
                self.advance()
            raise LexerError(text, 0, SourcePos(exc.pos, self.lineno, self.columnno))

    def advance(self):
        code = rutf8.codepoint_at_pos(self.text, self.pos)
        self.pos = rutf8.next_codepoint_pos(self.text, self.pos)
        if code == 10:
            self.lineno += 1
            self.columnno = 0
        else:
            self.columnno += 1

    def fail(self, start, line, column):
        raise LexerError(self.text, 0, SourcePos(start, line, column))

    def scan_block_comment(self, start, line, column):
        text = self.text
        size = len(text)
        self.advance()
        self.advance()
        while self.pos < size and not rstring.startswith(text, '*/', self.pos, size):
            self.advance()
        if self.pos == size:
            raise IncompleteTokenError(text, 0, SourcePos(start, line, column))
        self.advance()
        self.advance()

    def scan_quoted(self, start, line, column):
        text = self.text
        size = len(text)
        char = text[start]
        self.advance()
        while self.pos < size:
            c = text[self.pos]
            self.advance()
            if c == '\\':
                if self.pos < size:
                    escape = text[self.pos]
                    self.advance()
                    if escape == 'x' or '0' <= escape <= '7':
                        while self.pos < size and text[self.pos] != '\\':
                            self.advance()
                        if self.pos < size:
                            self.advance()
            elif c == char:
                if self.pos < size and text[self.pos] == char:
                    self.advance()
                else:
                    return
        raise IncompleteTokenError(text, 0, SourcePos(start, line, column))

    def scan_character_code(self, start, line, column):
        # The initial zero has been consumed; the cursor is on the quote.
        text = self.text
        size = len(text)
        self.advance()
        if self.pos == size:
            self.fail(start, line, column)
        if text[self.pos] == '\\':
            self.advance()
            if self.pos == size:
                self.fail(start, line, column)
            escape = text[self.pos]
            self.advance()
            if escape in 'uU':
                count = 4 if escape == 'u' else 8
                for unused in range(count):
                    if self.pos == size:
                        self.fail(start, line, column)
                    self.advance()
            elif escape == 'x' or '0' <= escape <= '7':
                while self.pos < size and text[self.pos] != '\\':
                    self.advance()
                if self.pos == size:
                    self.fail(start, line, column)
                self.advance()
        else:
            self.advance()

    def scan_decimal_digits(self):
        text = self.text
        while self.pos < len(text) and '0' <= text[self.pos] <= '9':
            self.advance()

    def scan_number(self, start, line, column):
        text = self.text
        size = len(text)
        char = text[start]
        self.advance()
        if char == '0' and self.pos < size and text[self.pos] == "'":
            self.scan_character_code(start, line, column)
            return 'NUMBER'
        self.scan_decimal_digits()
        if (self.pos + 1 >= size or text[self.pos] != '.' or
                not '0' <= text[self.pos + 1] <= '9'):
            return 'NUMBER'
        self.advance()
        self.scan_decimal_digits()
        if self.pos < size and text[self.pos] in 'eE':
            self.advance()
            if self.pos < size and text[self.pos] in '+-':
                self.advance()
            digits = self.pos
            self.scan_decimal_digits()
            if self.pos == digits:
                self.fail(start, line, column)
        return 'FLOAT'

    def scan_ascii_graphic(self, start, line, column):
        text = self.text
        size = len(text)
        for symbol in GRAPHIC_TOKENS:
            if rstring.startswith(text, symbol, start, size):
                for unused in range(len(symbol)):
                    self.advance()
                return
        self.fail(start, line, column)

    def find_next_token(self):
        text = self.text
        size = len(text)
        while self.pos < size:
            start = self.pos
            line = self.lineno
            column = self.columnno
            code = rutf8.codepoint_at_pos(text, start)
            char = text[start]
            name = 'ATOM'
            if utf8.layout(code) or (start == 0 and code == 0xfeff):
                self.advance()
                name = 'IGNORE'
            elif char == '%':
                while self.pos < size and text[self.pos] != '\n':
                    self.advance()
                name = 'IGNORE'
            elif rstring.startswith(text, '/*', start, size):
                self.scan_block_comment(start, line, column)
                name = 'IGNORE'
            elif char in "'\"":
                if char == '"':
                    name = 'STRING'
                self.scan_quoted(start, line, column)
            elif utf8.identifier_start(code):
                if utf8.variable_start(code):
                    name = 'VAR'
                self.advance()
                while self.pos < size and utf8.identifier_continue(
                        rutf8.codepoint_at_pos(text, self.pos)):
                    self.advance()
            elif '0' <= char <= '9':
                name = self.scan_number(start, line, column)
            elif rstring.startswith(text, '[]', start, size) or rstring.startswith(text, '{}', start, size):
                self.advance()
                self.advance()
            elif char in '()[]{}|.':
                name = char
                self.advance()
            elif char in '!,;':
                self.advance()
            elif code < 128:
                self.scan_ascii_graphic(start, line, column)
            elif utf8.unicode_solo(code):
                self.advance()
            else:
                self.fail(start, line, column)
            if name == 'IGNORE' and self.ignore_layout:
                continue
            return Token(name, text[start:self.pos], SourcePos(start, line, column))
        if self.eof:
            self.eof = False
            return Token('EOF', '', SourcePos(size, self.lineno, self.columnno))
        raise StopIteration
