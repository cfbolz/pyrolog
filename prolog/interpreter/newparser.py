import math
from rpython.rlib import rutf8
from rpython.rlib.rstring import ParseStringError
from prolog.interpreter import error, helper, term
from prolog.interpreter.parsing_helpers import unescape, parse_integer_literal

class ParseError(Exception):
    def __init__(self, msg, tok, parser):
        self.msg = msg
        self.tok = tok
        self.parser = parser


class Operator(object):
    def __init__(self, name, precedence, form):
        assert 1 <= precedence <= 1200
        self.name = name
        self.precedence = precedence
        self.form = form
        self.left_limit = self.right_limit = -1
        if form in ('yfx', 'xfy', 'xfx'):
            self.left_limit = precedence if form[0] == 'y' else precedence - 1
            self.right_limit = precedence if form[2] == 'y' else precedence - 1
            self.kind = 'infix'
        elif form in ('fx', 'fy'):
            self.right_limit = precedence if form[1] == 'y' else precedence - 1
            self.kind = 'prefix'
        elif form in ('xf', 'yf'):
            self.left_limit = precedence if form[0] == 'y' else precedence - 1
            self.kind = 'postfix'
        else:
            assert False, 'wrong form'

    def __repr__(self):
        return 'Operator(%r, %d, %r)' % (self.name, self.precedence, self.form)


class OperatorTable(object):
    def __init__(self):
        self.prefix_ops = {}
        self.infix_ops = {}
        self.postfix_ops = {}

    def add(self, name, precedence, form):
        operator = Operator(name, precedence, form)
        if operator.kind == 'prefix':
            self.prefix_ops[name] = operator
        elif operator.kind == 'infix':
            self.infix_ops[name] = operator
        else:
            self.postfix_ops[name] = operator


class ExpressionState(object):
    """Stacks for one expression; nested syntax gets a fresh instance."""
    def __init__(self, parser, max_precedence):
        self.parser = parser
        self.max_precedence = max_precedence
        self.terms = []
        self.precedences = []
        self.pending_tokens = []
        self.pending_operators = []

    def push_operand(self, value, precedence=0):
        self.terms.append(value)
        self.precedences.append(precedence)

    def push_operator(self, token, incoming):
        self._reduce_before(incoming)
        self.push_pending(token, incoming)

    def push_pending(self, token, incoming):
        self.pending_tokens.append(token)
        self.pending_operators.append(incoming)

    def _reduce_before(self, incoming):
        while self.pending_operators:
            previous = self.pending_operators[-1]
            if incoming.precedence <= previous.right_limit:
                break
            self._reduce()

    def reinterpret_pending(self, context_precedence):
        if self.pending_operators:
            operator = self.pending_operators[-1]
            if context_precedence <= operator.right_limit:
                return False
            if operator.kind == 'prefix':
                self._prefix_as_atom()
                return True
            if operator.kind == 'infix':
                postfix = self.parser.operators.postfix_ops.get(operator.name)
                if postfix is not None:
                    self.pending_operators[-1] = postfix
                    return True
        return False

    def _prefix_as_atom(self):
        operator = self.pending_operators.pop()
        self.pending_tokens.pop()
        self.push_operand(term.Callable.build(operator.name))

    def complete_operand(self, expect_operand, token):
        if expect_operand:
            # A lone operator name is an atom even in a restricted argument
            # context, e.g. f(p) where p is a prefix operator of priority 1100.
            if (not self.terms and len(self.pending_operators) == 1 and
                    self.pending_operators[0].kind == 'prefix'):
                self._prefix_as_atom()
            elif not self.reinterpret_pending(self.max_precedence + 1):
                self.parser._error('expected a term', token)

    def _reduce(self):
        operator = self.pending_operators.pop()
        token = self.pending_tokens.pop()
        if operator.precedence > self.max_precedence:
            self.parser._error('operator precedence exceeds expression limit', token)
        if operator.kind == 'infix':
            right = self.terms.pop()
            right_precedence = self.precedences.pop()
            left = self.terms.pop()
            left_precedence = self.precedences.pop()
            if (left_precedence > operator.left_limit or
                    right_precedence > operator.right_limit):
                self.parser._error('operand precedence clash', token)
            args = [left, right]
        elif operator.kind == 'prefix':
            right = self.terms.pop()
            right_precedence = self.precedences.pop()
            if right_precedence > operator.right_limit:
                self.parser._error('operand precedence clash', token)
            args = [right]
        else:
            assert operator.kind == 'postfix'
            left = self.terms.pop()
            left_precedence = self.precedences.pop()
            if left_precedence > operator.left_limit:
                self.parser._error('operand precedence clash', token)
            args = [left]
        self.push_operand(term.Callable.build(operator.name, args),
                          operator.precedence)

    def finish(self):
        while self.pending_operators:
            self._reduce()
        assert len(self.terms) == len(self.precedences) == 1
        return self.terms[0]


class Parser(object):
    def __init__(self, tokens, operators):
        self.tokens = tokens
        self.operators = operators
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
        res = self._parse_op_expr(1200, '.')
        self._expect(".")
        if self.position != len(self.tokens):
            self._error("unexpected token after full stop", self._peek())
        return res

    def _parse_op_expr(self, max_precedence, stops):
        state = ExpressionState(self, max_precedence)
        expect_operand = True
        while self.position < len(self.tokens):
            current = self._peek()
            if (current.name in stops or
                    current.name == 'ATOM' and current.source == ',' and ',' in stops):
                break
            if expect_operand:
                if (current.name == 'ATOM' and current.source == '-' and
                        self.position + 1 < len(self.tokens)):
                    number = self.tokens[self.position + 1]
                    if (number.name in ('NUMBER', 'FLOAT') and
                            number.source_pos.i == current.source_pos.i + 1):
                        self._get_next()
                        self._get_next()
                        state.push_operand(self._parse_negative_number(number))
                        expect_operand = False
                        continue
                if (current.name == 'ATOM' and not current.source.startswith("'")
                        and not self._starts_compound(current)):
                    prefix = self.operators.prefix_ops.get(current.source)
                    if prefix is not None and prefix.precedence <= max_precedence:
                        self._get_next()
                        state.push_pending(current, prefix)
                        continue
            incoming = self._select_operator(current, state, expect_operand)
            if incoming is None and expect_operand:
                state.push_operand(self._parse_expr())
                expect_operand = False
                continue
            if incoming is None:
                self._error('expected an operator', current)
            self._get_next()
            state.push_operator(current, incoming)
            expect_operand = incoming.kind == 'infix'
        current = self.tokens[self.position] if self.position < len(self.tokens) else None
        state.complete_operand(expect_operand, current)
        return state.finish()

    def _select_operator(self, token, state, expect_operand):
        if token.name != 'ATOM' or token.source.startswith("'"):
            return None
        if expect_operand and self._starts_compound(token):
            return None
        infix = self.operators.infix_ops.get(token.source)
        postfix = self.operators.postfix_ops.get(token.source)
        for incoming in [infix, postfix]:
            if incoming is not None:
                if not expect_operand or state.reinterpret_pending(incoming.left_limit):
                    return incoming
        return None

    def _starts_compound(self, token):
        if self.position + 1 == len(self.tokens):
            return False
        opening = self.tokens[self.position + 1]
        return (opening.name == '(' and
                opening.source_pos.i == token.source_pos.i + len(token.source))

    def _parse_expr(self):
        current = self._get_next()
        if current.name == "ATOM":
            if current.source == ',':
                self._error('expected a term', current)
            name = current.source
            if name.startswith("'"):
                end = len(name) - 1
                assert end >= 1
                name = self._unescape(name[1:end], current)
            args = self._parse_args(current)
            return term.Callable.build(name, args)
        if current.name == "NUMBER":
            return self._parse_number(current)
        if current.name == "FLOAT":
            return self._parse_float(current)
        if current.name == "STRING":
            return self._parse_string(current)
        if current.name == "(":
            res = self._parse_op_expr(1200, ')')
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
        if current.name == "{":
            if self._peek().name == "}":
                self._get_next()
                return term.Callable.build("{}")
            res = self._parse_op_expr(1200, '}')
            self._expect("}")
            return term.Callable.build("{}", [res])
        self._error("expected a term", current)

    def _unescape(self, text, current, quote="'"):
        try:
            return unescape(text, quote)
        except error.CatchableError:
            self._error("invalid character escape", current)

    def _parse_string(self, current):
        end = len(current.source) - 1
        assert end >= 1
        text = self._unescape(current.source[1:end], current, '"')
        codes = [term.Number(code) for code in rutf8.Utf8StringIterator(text)]
        return helper.wrap_list(codes)

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
            raise self._error("invalid float literal", current)
        except OverflowError:
            raise self._error("float overflow", current)
        if math.isinf(value):
            self._error("float overflow", current)
        return term.Float(value)

    def _parse_negative_number(self, current):
        if current.name == 'FLOAT':
            value = self._parse_float(current)
            return term.Float(-value.floatval)
        value = self._parse_number(current)
        if isinstance(value, term.Number):
            return term.Number(-value.num)
        assert isinstance(value, term.BigInt)
        negative = value.value.neg()
        try:
            return term.Number(negative.toint())
        except OverflowError:
            return term.BigInt(negative)

    def _parse_args(self, functor):
        # ( arg1 , ..., argn )
        next = self._peek()
        if next.name != "(":
            return []
        if next.source_pos.i != functor.source_pos.i + len(functor.source):
            return []
        self._get_next()
        res = []
        while 1:
            res.append(self._parse_op_expr(999, ',)'))
            next = self._peek()
            if next.name == ')':
                self._get_next()
                # Callable arguments must be a list that is never resized.
                return res[:]
            self._expect('ATOM', ',')

    def _parse_list(self):
        # The opening bracket has already been consumed.
        tail = term.Callable.build("[]")
        if self._peek().name == "]":
            self._get_next()
            return tail
        elements = []
        while True:
            elements.append(self._parse_op_expr(999, ',|]'))
            next = self._peek()
            if next.name == "]":
                self._get_next()
                break
            if next.name == "|":
                self._get_next()
                tail = self._parse_op_expr(999, ']')
                self._expect("]")
                break
            self._expect("ATOM", ",")
        for i in range(len(elements) - 1, -1, -1):
            tail = term.Callable.build(".", [elements[i], tail])
        return tail
