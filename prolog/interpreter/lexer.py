"""Code-point aware Prolog lexer with byte offsets into the original source."""
from rpython.rlib import rutf8, rstring
from rpython.rlib.parsing.lexer import Token, SourcePos
from prolog.interpreter.syntaxerror import SyntaxError, SourceSpan
from prolog.interpreter import utf8


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
            start = SourcePos(exc.pos, self.lineno, self.columnno)
            end = SourcePos(exc.pos + 1, self.lineno, self.columnno + 1)
            raise SyntaxError('invalid UTF-8 sequence', SourceSpan(start, end), 'invalid_utf8')

    def advance(self):
        code = rutf8.codepoint_at_pos(self.text, self.pos)
        self.pos = rutf8.next_codepoint_pos(self.text, self.pos)
        if code == 10:
            self.lineno += 1
            self.columnno = 0
        else:
            self.columnno += 1

    def fail(self, start, line, column):
        beginning = SourcePos(start, line, column)
        if self.pos == start:
            end = SourcePos(rutf8.next_codepoint_pos(self.text, start), line, column + 1)
        else:
            end = SourcePos(self.pos, self.lineno, self.columnno)
        raise SyntaxError('invalid token', SourceSpan(beginning, end), 'invalid_token')

    def unclosed(self, start, line, column, width, kind, expected):
        primary = SourceSpan(SourcePos(start, line, column),
                             SourcePos(start + width, line, column + width))
        end = SourcePos(self.pos, self.lineno, self.columnno)
        raise SyntaxError('expected %s before end of input' % expected, primary, kind,
                          SourceSpan(end, end), expected, 'EOF', incomplete=True,
                          primary_label='opened here',
                          secondary_label="expected '%s' here" % expected)

    def scan_block_comment(self, start, line, column):
        text = self.text
        size = len(text)
        self.advance()
        self.advance()
        while self.pos < size and not rstring.startswith(text, '*/', self.pos, size):
            self.advance()
        if self.pos == size:
            self.unclosed(start, line, column, 2, 'unclosed_comment', '*/')
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
        self.unclosed(start, line, column, 1, 'unclosed_quote', char)

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
        elif rstring.startswith(text, "''", self.pos, size):
            # A doubled quote denotes the quote character after the 0' prefix.
            self.advance()
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
        if char == '0' and self.pos < size and text[self.pos] in 'xob':
            prefix = text[self.pos]
            digits = '0123456789abcdef' if prefix == 'x' else (
                '01234567' if prefix == 'o' else '01')
            self.advance()
            first_digit = self.pos
            while self.pos < size and text[self.pos].lower() in digits:
                self.advance()
            if self.pos == first_digit:
                self.fail(start, line, column)
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

    def scan_ascii_graphic(self):
        text = self.text
        while self.pos < len(text) and utf8.ascii_graphic(ord(text[self.pos])):
            self.advance()

    def is_full_stop(self):
        following = self.pos + 1
        return (following == len(self.text) or self.text[following] == '%' or
                utf8.layout(rutf8.codepoint_at_pos(self.text, following)))

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
            elif char == '.' and self.is_full_stop():
                name = '.'
                self.advance()
            elif char in '()[]{}|':
                name = char
                self.advance()
            elif char in '!,;':
                self.advance()
            elif utf8.ascii_graphic(code):
                self.scan_ascii_graphic()
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
