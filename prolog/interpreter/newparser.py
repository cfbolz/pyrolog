from rpython.rlib.rstring import ParseStringOverflowError, ParseStringError
from rpython.rlib.rarithmetic import ovfcheck, string_to_int
from rpython.rlib.rbigint import rbigint
from prolog.interpreter import error, term
from prolog.interpreter.parsing import unescape

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
                try:
                    name = unescape(name[1:-1])
                except error.CatchableError:
                    self._error("invalid escape in quoted atom", current)
            args = self._parse_args()
            return term.Callable.build(name, args)
        return self._parse_expr()

    def _parse_expr(self):
        current = self._get_next()
        if current.name == "NUMBER":
            s = current.source
            try:
                intval = string_to_int(s)
            except ParseStringOverflowError: # overflow
                return term.BigInt(rbigint.fromdecimalstr(s))
            return term.Number(intval)
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
        self._error("expected a term", current)

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
