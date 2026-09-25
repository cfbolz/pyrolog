from rpython.rlib import rutf8
from prolog.interpreter.utf8 import unicodedb
from prolog.interpreter import utf8
import os
import string

from prolog.interpreter.term import Float, Number, Numeric, Var, Atom, Callable, AttVar, BindingVar
from prolog.interpreter import error, helper, parsing
from prolog.builtin.register import expose_builtin
from prolog.interpreter.signature import Signature
from prolog.interpreter.stream import PrologStream

conssig = Signature.getsignature(".", 2)
nilsig = Signature.getsignature("[]", 0)
tuplesig = Signature.getsignature(",", 2)


def join_operator_parts(parts):
    """Separate adjacent tokens that the lexer would otherwise merge."""
    result = []
    previous = ''
    for part in parts:
        if not part:
            continue
        if previous:
            last = rutf8.codepoint_at_pos(previous,
                        rutf8.prev_codepoint_pos(previous, len(previous)))
            first = rutf8.codepoint_at_pos(part, 0)
            if (utf8.ascii_graphic(last) and utf8.ascii_graphic(first) or
                    utf8.identifier_continue(last) and utf8.identifier_continue(first)):
                result.append(' ')
        result.append(part)
        previous = part
    return ''.join(result)


class CycleFactorizer(object):
    """Build an acyclic display graph without binding or changing the input."""
    def __init__(self):
        self.active = {}
        self.finished = {}
        self.bindings = []
        self.preferred = {}

    def visit(self, obj):
        todo = [(obj, False)]
        results = []
        while todo:
            obj, finishing = todo.pop()
            obj = obj.dereference(None)
            if not isinstance(obj, Callable) or obj.argument_count() == 0:
                results.append(obj)
            elif finishing:
                start = len(results) - obj.argument_count()
                assert start >= 0
                args = results[start:]
                del results[start:]
                result = Callable.build(obj.name(), args, signature=obj.signature())
                var = self.active.pop(obj)
                if var is not None:
                    self.bindings.append(Callable.build("=", [var, result]))
                    result = var
                self.finished[obj] = result
                results.append(result)
            elif obj in self.finished:
                results.append(self.finished[obj])
            elif obj in self.active:
                var = self.active[obj]
                if var is None:
                    var = self.preferred.get(obj)
                    if var is None:
                        var = BindingVar()
                    self.active[obj] = var
                results.append(var)
            else:
                self.active[obj] = None
                todo.append((obj, True))
                for i in range(obj.argument_count() - 1, -1, -1):
                    todo.append((obj.argument_at(i), False))
        assert len(results) == 1
        return results[0]

    def factorize(self, obj):
        template = self.visit(obj)
        return Callable.build("@", [template, helper.wrap_list(self.bindings)])


class TermFormatter(object):
    def __init__(self, engine, quoted=False, max_depth=0,
                 ignore_ops=False, cycles=True, module=None):
        self.engine = engine
        self.quoted = quoted
        self.max_depth = max_depth
        self.ignore_ops = ignore_ops
        self.cycles = cycles
        if module is None:
            module = engine.modulewrapper.current_module
        self._make_reverse_op_mapping(module.operators)
        self.var_to_number = {}
        self.variable_names = {}
        self.active_attvars = {}
    
    def from_option_list(engine, options, module=None):
        # XXX add numbervars support
        quoted = False
        max_depth = 0
        ignore_ops = False
        cycles = True
        number_vars = False
        for option in options:
            option, arg = helper.unwrap_option(option, 'write_option')
            if option.name()== "max_depth":
                try:
                    max_depth = helper.unwrap_int(arg)
                except error.CatchableError:
                    error.throw_domain_error('write_option', option)
            elif (not isinstance(arg, Atom) or
                (arg.name()!= "true" and arg.name()!= "false")):
                error.throw_domain_error('write_option', option)
                assert 0, "unreachable"
            elif option.name()== "quoted":
                quoted = arg.name()== "true"
            elif option.name()== "ignore_ops":
                ignore_ops = arg.name()== "true"
            elif option.name()== "cycles":
                cycles = arg.name()== "true"
        return TermFormatter(engine, quoted, max_depth, ignore_ops, cycles, module)
    from_option_list = staticmethod(from_option_list)

    def format(self, term, depth=1):
        if self.max_depth <= 0 or not self.cycles:
            from prolog.builtin.type import impl_acyclic_term
            try:
                impl_acyclic_term(self.engine, None, term)
            except error.UnificationFailed:
                if not self.cycles:
                    error.throw_domain_error("cyclic_term", term)
                term = CycleFactorizer().factorize(term)
        return self._format(term, depth)

    def format_with_cycles(self, term):
        # Diagnostics factor cycles before applying the normal depth limit.
        # Use the iterative factorizer directly, even for deep finite terms.
        factorizer = CycleFactorizer()
        display = factorizer.visit(term)
        if factorizer.bindings:
            display = factorizer.factorize(term)
        return self._format(display, 1)

    def _format(self, term, depth):
        if self.max_depth > 0 and depth > self.max_depth:
            return "..."
        term = term.dereference(None)
        if isinstance(term, Atom):
            return self.format_atom(term.name())
        elif isinstance(term, Number):
            return self.format_number(term)
        elif isinstance(term, Float):
            return self.format_float(term)
        elif helper.is_term(term):
            assert isinstance(term, Callable)
            return self.format_term(term, depth)
        elif isinstance(term, AttVar):
            return self.format_attvar(term, depth)
        elif isinstance(term, Var):
            return self.format_var(term)
        elif isinstance(term, PrologStream):
            return self.format_stream(term)
        else:
            return '?'

    def format_atom(self, s):
        from prolog.interpreter.syntaxerror import SyntaxError
        if self.quoted:
            try:
                tokens = parsing.lexer.tokenize(s)
                if (len(tokens) == 1 and tokens[0].name == 'ATOM' and
                    tokens[0].source == s and s != ',' and not s.startswith("'")):
                    return s
            except SyntaxError:
                pass
            parts = []
            for code in rutf8.Utf8StringIterator(s):
                if code == 39 or code == 92:
                    parts.append("\\" + chr(code))
                elif unicodedb.category(code).startswith('C') or code in (0x2028, 0x2029):
                    if code <= 0xffff:
                        prefix, width = '\\u', 4
                    else:
                        prefix, width = '\\U', 8
                    digits = '%x' % code
                    parts.append(prefix + '0' * (width - len(digits)) + digits)
                else:
                    parts.append(rutf8.unichr_as_utf8(code))
            return "'%s'" % "".join(parts)
        return s

    def format_number(self, num):
        return str(num.num)

    def format_float(self, num):
        return str(num.floatval)

    def format_attvar(self, attvar, depth):
        if self.max_depth > 0:
            return self._format_attvar(attvar, depth)
        # Attribute payloads are not part of the ordinary term graph. Keep the
        # existing put_attr display, referring back by name on recursive visits.
        if attvar in self.active_attvars:
            return self.format_var(attvar)
        self.active_attvars[attvar] = None
        try:
            return self._format_attvar(attvar, depth)
        finally:
            del self.active_attvars[attvar]

    def _format_attvar(self, attvar, depth):
        l = []
        if attvar.value_list is not None:
            for name, index in attvar.attmap.indexes.iteritems():
                value = attvar.value_list[index]
                if value is not None:
                    l.append("put_attr(%s, %s, %s)" % (self.format_var(attvar),
                            name, self.format(value, depth + 1)))
        return "\n".join(l)

    def format_var(self, var):
        name = self.variable_names.get(var)
        if name is not None:
            return name
        try:
            num = self.var_to_number[var]
        except KeyError:
            num = self.var_to_number[var] = len(self.var_to_number)
        return "_G%s" % (num, )

    def format_term_normally(self, term, depth):
        return "%s(%s)" % (self.format_atom(term.name()),
                           ", ".join([self._format(a, depth + 1) for a in term.arguments()]))

    def format_term(self, term, depth):
        if self.ignore_ops:
            return self.format_term_normally(term, depth)
        else:
            return self.format_with_ops(term, depth)[1]

    def format_stream(self, stream):
        return "'$stream'(%d)" % stream.fd()

    def format_with_ops(self, term, depth):
        if self.max_depth > 0 and depth > self.max_depth:
            return (0, "...")
        term = term.dereference(None)
        if not helper.is_term(term):
            return (0, self._format(term, depth))
        assert isinstance(term, Callable)
        if term.signature().eq(conssig):
            result = ["["]
            while helper.is_term(term) and isinstance(term, Callable) and term.signature().eq(conssig):
                first = term.argument_at(0)
                second = term.argument_at(1).dereference(None)
                result.append(self._format(first, depth + 1))
                result.append(", ")
                term = second
                depth += 1
                if (self.max_depth > 0 and depth >= self.max_depth and
                    not (isinstance(term, Atom) and term.signature().eq(nilsig))):
                    result[-1] = "|...]"
                    return (0, "".join(result))
            if isinstance(term, Atom) and term.signature().eq(nilsig):
                result[-1] = "]"
            else:
                result[-1] = "|"
                result.append(self._format(term, depth))
                result.append("]")
            return (0, "".join(result))
        if term.signature().eq(tuplesig):
            result = ["("]
            while (helper.is_term(term) and isinstance(term, Callable) and
                   term.signature().eq(tuplesig) and
                   (self.max_depth <= 0 or depth <= self.max_depth)):
                first = term.argument_at(0)
                second = term.argument_at(1).dereference(None)
                result.append(self._format_operand(first, depth + 1, 999))
                result.append(", ")
                term = second
                depth += 1
            result.append(self._format_operand(term, depth, 1000))
            result.append(")")
            return (0, "".join(result))
        if (term.argument_count(), term.name()) not in self.op_mapping:
            return (0, self.format_term_normally(term, depth))
        if self.quoted and self.format_atom(term.name()) != term.name():
            # Quoted names are functors, never operators, in the parser.
            return (0, self.format_term_normally(term, depth))
        form, prec = self.op_mapping[(term.argument_count(), term.name())]
        result = []
        assert 0 <= term.argument_count() <= 2
        curr_index = 0
        for c in form:
            if c == "f":
                result.append(self.format_atom(term.name()))
            else:
                operand = term.argument_at(curr_index).dereference(None)
                limit = prec - 1 if c == 'x' else prec
                child = self._format_operand(operand, depth + 1, limit)
                if form[0] == 'f' and (child.startswith('(') or
                        term.name() == '-' and isinstance(operand, Numeric)):
                    # Adjacent '(' starts a compound call; adjacent '-1' is a
                    # numeric literal rather than a unary '-' application.
                    result.append(' ')
                result.append(child)
                curr_index += 1
        assert curr_index == term.argument_count()
        return (prec, join_operator_parts(result))

    def _format_operand(self, operand, depth, limit):
        if self.max_depth > 0 and depth > self.max_depth:
            return '...'
        operand = operand.dereference(None)
        precedence, text = self.format_with_ops(operand, depth)
        parentheses = precedence > limit
        if isinstance(operand, Atom) and (
                (1, operand.name()) in self.op_mapping or
                (2, operand.name()) in self.op_mapping):
            # Atom precedence alone cannot protect an operator name from being
            # reinterpreted in its parent's expression.
            parentheses = True
        elif isinstance(operand, Callable) and operand.argument_count() == 1:
            if operand.name() in self.ambiguous_postfix:
                # Terminate the child expression before a following operator
                # can make its postfix name look like an infix application.
                parentheses = True
        if parentheses:
            return '(' + text + ')'
        return text

    def _make_reverse_op_mapping(self, operators):
        m = {}
        for operator in operators.all_operators():
            key = (len(operator.form) - 1, operator.name)
            # Preserve the formatter's preference for tighter unary operators
            # when a name has both prefix and postfix declarations.
            if key not in m or operator.precedence <= m[key][1]:
                m[key] = (operator.form, operator.precedence)
        self.op_mapping = m
        self.ambiguous_postfix = {}
        for name in operators.postfix_ops:
            form, precedence = m[(1, name)]
            if form in ('xf', 'yf') and name in operators.infix_ops:
                self.ambiguous_postfix[name] = None
