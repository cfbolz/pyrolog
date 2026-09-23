"""Code-point aware Prolog lexer with byte offsets into the original source."""
from rpython.rlib import rutf8
from rpython.rlib.parsing.lexer import Token, SourcePos
from rpython.rlib.parsing.deterministic import LexerError
from prolog.interpreter import utf8


# Retain the existing ASCII operator tokenization, including :/ predicate indicators.
GRAPHIC_TOKENS = sorted([
    '-->', ':-', '?-', '->', '\\+', '~', '<', '=', '=..', '=@=', '=:=',
    '=<', '==', '=\\=', '>', '?=', '>=', '@<', '@=<', '@>', '@>=',
    '\\=', '\\==', ':', '+', '-', '/\\', '\\/', '?', '\\', '*', '/',
    '//', '<<', '>>', '**', '^'], key=len, reverse=True)


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
            raise LexerError(text, 0, SourcePos(exc.pos, 0, 0))

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
            elif text.startswith('/*', start):
                self.advance()
                self.advance()
                while self.pos < size and not text.startswith('*/', self.pos):
                    self.advance()
                if self.pos == size:
                    self.fail(start, line, column)
                self.advance()
                self.advance()
                name = 'IGNORE'
            elif char in "'\"":
                if char == '"':
                    name = 'STRING'
                self.advance()
                closed = False
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
                            closed = True
                            break
                if not closed:
                    self.fail(start, line, column)
            elif utf8.identifier_start(code):
                if utf8.variable_start(code):
                    name = 'VAR'
                self.advance()
                while self.pos < size and utf8.identifier_continue(
                        rutf8.codepoint_at_pos(text, self.pos)):
                    self.advance()
            elif '0' <= char <= '9':
                name = 'NUMBER'
                self.advance()
                if char == '0' and self.pos < size and text[self.pos] == "'":
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
                    else:
                        self.advance()
                else:
                    while self.pos < size and '0' <= text[self.pos] <= '9':
                        self.advance()
                    if (self.pos + 1 < size and text[self.pos] == '.' and
                            '0' <= text[self.pos + 1] <= '9'):
                        name = 'FLOAT'
                        self.advance()
                        while self.pos < size and '0' <= text[self.pos] <= '9':
                            self.advance()
                        if self.pos < size and text[self.pos] in 'eE':
                            self.advance()
                            if self.pos < size and text[self.pos] in '+-':
                                self.advance()
                            digits = self.pos
                            while self.pos < size and '0' <= text[self.pos] <= '9':
                                self.advance()
                            if self.pos == digits:
                                self.fail(start, line, column)
            elif text.startswith('[]', start) or text.startswith('{}', start):
                self.advance()
                self.advance()
            elif char in '()[]{}|.':
                name = char
                self.advance()
            elif char in '!,;':
                self.advance()
            elif code < 128:
                matched = False
                for symbol in GRAPHIC_TOKENS:
                    if text.startswith(symbol, start):
                        for unused in range(len(symbol)):
                            self.advance()
                        matched = True
                        break
                if not matched:
                    self.fail(start, line, column)
            elif utf8.graphic(code):
                self.advance()
                while self.pos < size:
                    following = rutf8.codepoint_at_pos(text, self.pos)
                    if following < 128 or not utf8.graphic(following):
                        break
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
