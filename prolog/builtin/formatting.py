import os
import string

from prolog.interpreter.term import Float, Number, Var, Atom, Callable, AttVar, BindingVar
from prolog.interpreter import error, helper, parsing
from prolog.builtin.register import expose_builtin
from prolog.interpreter.signature import Signature
from prolog.interpreter.stream import PrologStream

conssig = Signature.getsignature(".", 2)
nilsig = Signature.getsignature("[]", 0)
tuplesig = Signature.getsignature(",", 2)


class CycleFactorizer(object):
    """Build an acyclic display graph without binding or changing the input."""
    def __init__(self):
        self.active = {}
        self.finished = {}
        self.bindings = []

    def visit(self, obj):
        obj = obj.dereference(None)
        if not isinstance(obj, Callable) or obj.argument_count() == 0:
            return obj
        if obj in self.finished:
            return self.finished[obj]
        if obj in self.active:
            var = self.active[obj]
            if var is None:
                var = BindingVar()
                self.active[obj] = var
            return var
        self.active[obj] = None
        args = [self.visit(obj.argument_at(i))
                for i in range(obj.argument_count())]
        result = Callable.build(obj.name(), args, signature=obj.signature())
        var = self.active.pop(obj)
        if var is not None:
            self.bindings.append(Callable.build("=", [var, result]))
            result = var
        self.finished[obj] = result
        return result

    def factorize(self, obj):
        template = self.visit(obj)
        return Callable.build("@", [template, helper.wrap_list(self.bindings)])


class TermFormatter(object):
    def __init__(self, engine, quoted=False, max_depth=0,
                 ignore_ops=False, cycles=True):
        self.engine = engine
        self.quoted = quoted
        self.max_depth = max_depth
        self.ignore_ops = ignore_ops
        self.cycles = cycles
        self._make_reverse_op_mapping()
        self.var_to_number = {}
        self.active_attvars = {}
    
    def from_option_list(engine, options):
        # XXX add numbervars support
        quoted = False
        max_depth = 0
        ignore_ops = False
        cycles = True
        number_vars = False
        for option in options:
            if (not helper.is_term(option) or (isinstance(option, Callable) and option.argument_count() != 1)):
                error.throw_domain_error('write_option', option)
            assert isinstance(option, Callable)
            arg = option.argument_at(0)
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
        return TermFormatter(engine, quoted, max_depth, ignore_ops, cycles)
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
        from rpython.rlib.parsing.deterministic import LexerError
        if self.quoted:
            try:
                tokens = parsing.lexer.tokenize(s)
                if (len(tokens) == 1 and tokens[0].name == 'ATOM' and
                    tokens[0].source == s):
                    return s
            except LexerError:
                pass
            return "'%s'" % (s, )
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
                result.append(self._format(first, depth + 1))
                result.append(", ")
                term = second
                depth += 1
            result.append(self._format(term, depth))
            result.append(")")
            return (0, "".join(result))
        if (term.argument_count(), term.name()) not in self.op_mapping:
            return (0, self.format_term_normally(term, depth))
        form, prec = self.op_mapping[(term.argument_count(), term.name())]
        result = []
        assert 0 <= term.argument_count() <= 2
        curr_index = 0
        for c in form:
            if c == "f":
                result.append(self.format_atom(term.name()))
            else:
                childprec, child = self.format_with_ops(term.argument_at(curr_index), depth + 1)
                parentheses = (c == "x" and childprec >= prec or
                               c == "y" and childprec > prec)
                if parentheses:
                    result.append("(")
                    result.append(child)
                    result.append(")")
                else:
                    result.append(child)
                curr_index += 1
        assert curr_index == term.argument_count()
        return (prec, "".join(result))

    def _make_reverse_op_mapping(self):
        m = {}
        for prec, allops in self.engine.getoperations():
            for form, ops in allops:
                for op in ops:
                    m[len(form) - 1, op] = (form, prec)
        self.op_mapping = m
