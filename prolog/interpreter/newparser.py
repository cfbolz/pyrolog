import math
from rpython.rlib import rutf8
from rpython.rlib.rstring import ParseStringError
from prolog.interpreter import error, term
from prolog.interpreter.parsing import unescape, parse_integer_literal

class ParseError(Exception):
    def __init__(self, msg, tok, parser):
        self.msg = msg
        self.tok = tok
        self.parser = parser


class Parser(object):
    def __init__(self, tokens, operators):
        self.tokens = tokens
        self.operators = operators
        assert not operators
        self.position = 0

        self.varname_to_var = {}

    def parse(self):
        return self._parse_toplevel()

    def _get_next(self):
        res = self._peek()
        self.position += 1
        return res

    def _peek(self):
        if self.position == len(self.tokens):
            self._error("unexpected end of input", None)
        return self.tokens[self.position]

    def _error(self, msg, tok):
        raise ParseError(msg, tok, self)

    def _expect(self, name, source=None):
        tok = self._get_next()
        if tok.name != name:
            self._error("expected %s got %s" % (name, tok.name), tok)
        if source is not None and tok.source != source:
            self._error("expected %s got %s" % (source, tok.name), tok)

    def _parse_toplevel(self):
        res = self._parse_toplevel_op_expr()
        self._expect(".")
        if self.position != len(self.tokens):
            self._error("unexpected token after full stop", self._peek())
        return res

    def _parse_toplevel_op_expr(self):
        current = self._peek()
        if current.name == "ATOM":
            self._get_next()
            name = current.source
            if name.startswith("'"):
                name = self._unescape(name[1:-1], current)
            args = self._parse_args()
            return term.Callable.build(name, args)
        return self._parse_expr()

    def _parse_expr(self):
        current = self._get_next()
        if current.name == "NUMBER":
            return self._parse_number(current)
        if current.name == "FLOAT":
            return self._parse_float(current)
        if current.name == "(":
            res = self._parse_toplevel_op_expr()
            self._expect(")")
            return res
        if current.name == "VAR":
            varname = current.source
            if varname == "_":
                return term.BindingVar()
            if varname in self.varname_to_var:
                return self.varname_to_var[varname]
            res = term.BindingVar()
            self.varname_to_var[varname] = res
            return res
        if current.name == "[":
            return self._parse_list()
        self._error("expected a term", current)

    def _unescape(self, text, current):
        try:
            return unescape(text)
        except error.CatchableError:
            self._error("invalid character escape", current)

    def _parse_number(self, current):
        s = current.source
        if s.startswith("0'"):
            char = self._unescape(s[2:], current)
            if rutf8.codepoints_in_utf8(char) != 1:
                self._error("expected one character", current)
            return term.Number(rutf8.codepoint_at_pos(char, 0))
        try:
            return parse_integer_literal(s)
        except ParseStringError:
            self._error("invalid integer literal", current)

    def _parse_float(self, current):
        try:
            value = float(current.source)
        except ValueError:
            self._error("invalid float literal", current)
        except OverflowError:
            self._error("float overflow", current)
        if math.isinf(value):
            self._error("float overflow", current)
        return term.Float(value)

    def _parse_args(self):
        # ( arg1 , ..., argn )
        next = self._peek()
        if next.name != "(":
            return []
        self._get_next()
        res = []
        while 1:
            res.append(self._parse_toplevel_op_expr())
            next = self._peek()
            if next.name == ')':
                self._get_next()
                return res
            self._expect('ATOM', ',')

    def _parse_list(self):
        # The opening bracket has already been consumed.
        tail = term.Callable.build("[]")
        if self._peek().name == "]":
            self._get_next()
            return tail
        elements = []
        while True:
            elements.append(self._parse_toplevel_op_expr())
            next = self._peek()
            if next.name == "]":
                self._get_next()
                break
            if next.name == "|":
                self._get_next()
                tail = self._parse_toplevel_op_expr()
                self._expect("]")
                break
            self._expect("ATOM", ",")
        for i in range(len(elements) - 1, -1, -1):
            tail = term.Callable.build(".", [elements[i], tail])
        return tail
