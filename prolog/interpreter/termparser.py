import math
from rpython.rlib import rutf8
from rpython.rlib.rstring import ParseStringError
from rpython.rlib.parsing.lexer import Token, SourcePos
from prolog.interpreter import helper, term
from prolog.interpreter.syntaxerror import SyntaxError, SourceSpan, token_span, token_position
from prolog.interpreter.parsing_helpers import unescape_literal, EscapeError, parse_integer_literal

CLOSING_DELIMITERS = {'(': ')', '[': ']', '{': '}'}

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
        self._table_for_form(form)[name] = operator

    def _table_for_form(self, form):
        if form in ('fx', 'fy'):
            return self.prefix_ops
        if form in ('xfx', 'xfy', 'yfx'):
            return self.infix_ops
        assert form in ('xf', 'yf')
        return self.postfix_ops

    def remove(self, name, form):
        table = self._table_for_form(form)
        if name in table:
            del table[name]

    def all_operators(self):
        return (self.prefix_ops.values() + self.infix_ops.values() +
                self.postfix_ops.values())


class ExpressionState(object):
    """Stacks for one expression; nested syntax gets a fresh instance."""
    def __init__(self, parser, max_precedence):
        self.parser = parser
        self.max_precedence = max_precedence
        self.terms = []
        self.precedences = []
        self.operand_tokens = []
        self.pending_tokens = []
        self.pending_operators = []

    def push_operand(self, value, precedence=0, token=None):
        self.terms.append(value)
        self.precedences.append(precedence)
        self.operand_tokens.append(token)

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
        token = self.pending_tokens.pop()
        self.push_operand(term.Callable.build(operator.name), token=token)

    def complete_operand(self, expect_operand, token, context):
        if expect_operand:
            # A lone operator name is an atom even in a restricted argument
            # context, e.g. f(p) where p is a prefix operator of priority 1100.
            if (not self.terms and len(self.pending_operators) == 1 and
                    self.pending_operators[0].kind == 'prefix'):
                self._prefix_as_atom()
            elif not self.reinterpret_pending(self.max_precedence + 1):
                if self.pending_tokens:
                    operator_token = self.pending_tokens[-1]
                    self.parser._error("expected a right operand for operator '%s'" %
                                       operator_token.source, operator_token,
                                       'missing_operand', token or self.parser.eof,
                                       expected='term',
                                       found=token.source if token is not None else 'EOF',
                                       primary_label='requires a right operand',
                                       secondary_label='expected a term here')
                self.parser._missing_term(token, context)

    def _reduce(self):
        operator = self.pending_operators.pop()
        token = self.pending_tokens.pop()
        if operator.precedence > self.max_precedence:
            self.parser._error("operator '%s' has precedence %d, exceeding expression limit %d" %
                               (operator.name, operator.precedence, self.max_precedence),
                               token, 'precedence_limit',
                               expected='at most %d' % self.max_precedence,
                               found=str(operator.precedence))
        if operator.kind == 'infix':
            right = self.terms.pop()
            right_precedence = self.precedences.pop()
            right_token = self.operand_tokens.pop()
            left = self.terms.pop()
            left_precedence = self.precedences.pop()
            left_token = self.operand_tokens.pop()
            self._check_precedence(operator, token, left_precedence,
                                   operator.left_limit, left_token, 'left')
            self._check_precedence(operator, token, right_precedence,
                                   operator.right_limit, right_token, 'right')
            args = [left, right]
        elif operator.kind == 'prefix':
            right = self.terms.pop()
            right_precedence = self.precedences.pop()
            right_token = self.operand_tokens.pop()
            self._check_precedence(operator, token, right_precedence,
                                   operator.right_limit, right_token, 'right')
            args = [right]
        else:
            assert operator.kind == 'postfix'
            left = self.terms.pop()
            left_precedence = self.precedences.pop()
            left_token = self.operand_tokens.pop()
            self._check_precedence(operator, token, left_precedence,
                                   operator.left_limit, left_token, 'left')
            args = [left]
        self.push_operand(term.Callable.build(operator.name, args),
                          operator.precedence, token)

    def _check_precedence(self, operator, token, precedence, limit, operand_token, side):
        if precedence > limit:
            self.parser._error("%s operand of '%s' (%s, precedence %d) has precedence %d; "
                               'expected at most %d' %
                               (side, operator.name, operator.form, operator.precedence,
                                precedence, limit), token, 'precedence_clash', operand_token,
                               expected='at most %d' % limit, found=str(precedence),
                               primary_label='%s operand requires precedence at most %d' % (side, limit),
                               secondary_label='operand has precedence %d' % precedence)

    def finish(self):
        while self.pending_operators:
            self._reduce()
        assert len(self.terms) == len(self.precedences) == len(self.operand_tokens) == 1
        return self.terms[0]


class Parser(object):
    def __init__(self, tokens, operators):
        # Supplying the lexer's EOF token preserves trailing layout positions.
        # Token-only callers otherwise get the end of their last token.
        if tokens and tokens[-1].name == 'EOF':
            self.eof = tokens[-1]
            end_index = len(tokens) - 1
            assert end_index >= 0
            tokens = tokens[:end_index]
        else:
            end = token_span(tokens[-1]).end if tokens else SourcePos(0, 0, 0)
            self.eof = Token('EOF', '', end)
        self.tokens = tokens
        self.operators = operators
        self.position = 0
        self.open_delimiters = []

        self.varname_to_var = {}

    def parse(self):
        return self._parse_toplevel()

    def _get_next(self):
        res = self._peek()
        self.position += 1
        return res

    def _peek(self):
        if self.position == len(self.tokens):
            self._check_delimiter(self.eof)
            self._error("unexpected end of input", None, 'unexpected_eof')
        token = self.tokens[self.position]
        self._check_delimiter(token)
        return token

    def _check_delimiter(self, token):
        if token.name not in (')', ']', '}', '.', 'EOF'):
            return
        if not self.open_delimiters:
            if token.name in (')', ']', '}'):
                self._error('unexpected closing delimiter %s' % token.name,
                                 token, 'unexpected_closing_delimiter',
                                 found=token.name)
            return
        opening = self.open_delimiters[-1]
        expected = CLOSING_DELIMITERS[opening.name]
        if token.name in ('.', 'EOF'):
            self._error('unclosed %s: expected %s' % (opening.name, expected),
                             opening, 'unclosed_delimiter', token,
                             expected, token.name, primary_label='opened here',
                             secondary_label="expected '%s' here" % expected)
        if token.name != expected:
            self._error('expected %s, found %s' % (expected, token.name),
                             token, 'mismatched_delimiter', opening,
                             expected, token.name,
                             primary_label="expected '%s' here" % expected,
                             secondary_label='opened here')

    def _error(self, msg, tok, kind='syntax_error', secondary=None, expected='', found='',
               primary_label='', secondary_label=''):
        if not found:
            found = 'EOF' if tok is None or tok.name == 'EOF' else tok.source
        primary_span = token_span(tok if tok is not None else self.eof)
        secondary_span = token_span(secondary) if secondary is not None else None
        incomplete = (kind in ('unclosed_delimiter', 'missing_operand') and
                      secondary is not None and secondary.name == 'EOF' or
                      found == 'EOF' and kind in ('missing_full_stop', 'unexpected_eof',
                                                 'missing_term'))
        raise SyntaxError(msg, primary_span, kind, secondary_span, expected, found, incomplete,
                          primary_label, secondary_label)

    def _missing_term(self, token, context='term'):
        opening = self.open_delimiters[-1] if self.open_delimiters else None
        description = 'an argument' if context == 'argument' else 'a ' + context.replace('_', ' ')
        self._error('expected %s' % context.replace('_', ' '), token,
                    'missing_' + context, opening, expected='term',
                    primary_label='expected %s here' % description,
                    secondary_label='opened here' if opening is not None else '')

    def _expect(self, name, source=None):
        if self.position == len(self.tokens):
            self._check_delimiter(self.eof)
            kind = 'missing_full_stop' if name == '.' else 'unexpected_eof'
            self._error('expected %s' % name, self.eof, kind, expected=name)
        tok = self._get_next()
        if tok.name != name or source is not None and tok.source != source:
            expected = source if source is not None else name
            self._error("expected '%s', found '%s'" % (expected, tok.source), tok,
                        'unexpected_token', expected=expected)
        if name in (')', ']', '}'):
            self.open_delimiters.pop()

    def _parse_toplevel(self):
        res = self._parse_op_expr(1200, '.')
        self._expect(".")
        if self.position != len(self.tokens):
            self._error("unexpected token after full stop", self._peek(),
                        'trailing_input', self.tokens[self.position - 1],
                        primary_label='unexpected input', secondary_label='term ended here')
        return res

    def _parse_op_expr(self, max_precedence, stops, context='term'):
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
                        state.push_operand(self._parse_negative_number(number), token=current)
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
                state.push_operand(self._parse_expr(), token=current)
                expect_operand = False
                continue
            if incoming is None:
                previous = self.tokens[self.position - 1] if self.position else None
                if (current.name == '(' and previous is not None and previous.name == 'ATOM'
                        and state.terms and isinstance(state.terms[-1], term.Atom)
                        and state.operand_tokens[-1] is previous):
                    self._error("expected an operator; '(' must immediately follow a functor name",
                                current, 'functor_whitespace', previous,
                                primary_label='whitespace before this parenthesis',
                                secondary_label='functor name here')
                if context == 'argument':
                    self._error("expected an operator or ',' between arguments",
                                current, 'missing_separator', previous,
                                expected="operator or ','", primary_label='unexpected term',
                                secondary_label='preceding argument ends here')
                if context == 'list_element':
                    self._error("expected an operator, ',' or '|' between list elements",
                                current, 'missing_separator', previous,
                                expected="operator, ',' or '|'", primary_label='unexpected term',
                                secondary_label='preceding list element ends here')
                self._error('expected an operator between terms', current,
                            'missing_operator', previous, expected='operator',
                            primary_label='unexpected term', secondary_label='preceding term ends here')
            self._get_next()
            state.push_operator(current, incoming)
            expect_operand = incoming.kind == 'infix'
        current = self.tokens[self.position] if self.position < len(self.tokens) else None
        if current is None:
            self._check_delimiter(self.eof)
        state.complete_operand(expect_operand, current, context)
        return state.finish()

    def _select_operator(self, token, state, expect_operand):
        if token.name not in ('ATOM', '|') or token.source.startswith("'"):
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
                self._missing_term(current)
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
            self.open_delimiters.append(current)
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
            self.open_delimiters.append(current)
            return self._parse_list()
        if current.name == "{":
            self.open_delimiters.append(current)
            if self._peek().name == "}":
                self._expect('}')
                return term.Callable.build("{}")
            res = self._parse_op_expr(1200, '}')
            self._expect("}")
            return term.Callable.build("{}", [res])
        self._missing_term(current)

    def _unescape(self, text, current, quote="'", offset=1):
        try:
            return unescape_literal(text, quote)
        except EscapeError as exc:
            kind = 'invalid_escape'
            message = 'invalid character escape'
            if exc.reason == 'character_code':
                kind = 'invalid_character_code'
                message = 'escape does not denote a Unicode scalar value'
            diagnostic = SyntaxError(message, token_span(current), kind)
            diagnostic.primary = SourceSpan(token_position(current, offset + exc.start),
                                            token_position(current, offset + exc.end))
            raise diagnostic

    def _parse_string(self, current):
        end = len(current.source) - 1
        assert end >= 1
        text = self._unescape(current.source[1:end], current, '"')
        codes = [term.Number(code) for code in rutf8.Utf8StringIterator(text)]
        return helper.wrap_list(codes)

    def _parse_number(self, current):
        s = current.source
        if s.startswith("0'"):
            char = self._unescape(s[2:], current, offset=2)
            if rutf8.codepoints_in_utf8(char) != 1:
                self._error("character-code literal must contain exactly one character",
                            current, 'invalid_character_literal')
            return term.Number(rutf8.codepoint_at_pos(char, 0))
        try:
            return parse_integer_literal(s)
        except ParseStringError:
            self._error("invalid integer literal", current, 'invalid_integer')

    def _parse_float(self, current):
        try:
            value = float(current.source)
        except ValueError:
            raise self._error("invalid float literal", current, 'invalid_float')
        except OverflowError:
            raise self._error("float overflow", current, 'float_overflow')
        if math.isinf(value):
            self._error("float overflow", current, 'float_overflow')
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
        if self.position == len(self.tokens):
            return []
        next = self._peek()
        if next.name != "(":
            return []
        if next.source_pos.i != functor.source_pos.i + len(functor.source):
            return []
        self._get_next()
        self.open_delimiters.append(next)
        res = []
        while 1:
            # Like SWI's default mode, allow all operator priorities here;
            # the unparenthesized comma still separates arguments.
            res.append(self._parse_op_expr(1200, ',)', 'argument'))
            next = self._peek()
            if next.name == ')':
                self._expect(')')
                # Callable arguments must be a list that is never resized.
                return res[:]
            self._expect('ATOM', ',')

    def _parse_list(self):
        # The opening bracket has already been consumed.
        tail = term.Callable.build("[]")
        if self._peek().name == "]":
            self._expect(']')
            return tail
        elements = []
        while True:
            elements.append(self._parse_op_expr(1200, ',|]', 'list_element'))
            next = self._peek()
            if next.name == "]":
                self._expect(']')
                break
            if next.name == "|":
                bar = self._get_next()
                tail = self._parse_op_expr(1200, ',|]', 'list_tail')
                if self._peek().name != ']':
                    self._error("expected ']' after list tail", self._peek(),
                                'invalid_list_tail', bar, expected=']',
                                primary_label="expected ']' here",
                                secondary_label='list tail starts after this')
                self._expect("]")
                break
            self._expect("ATOM", ",")
        for i in range(len(elements) - 1, -1, -1):
            tail = term.Callable.build(".", [elements[i], tail])
        return tail
