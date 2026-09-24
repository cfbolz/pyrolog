import py
import math
from rpython.rlib.parsing.deterministic import LexerError
from rpython.rlib.parsing.tree import Nonterminal, Symbol, RPythonVisitor
from rpython.rlib.parsing.parsing import PackratParser, LazyParseTable, Rule
from rpython.rlib.parsing.parsing import ParseError, ErrorInformation
from rpython.rlib.rstring import ParseStringOverflowError, ParseStringError
from rpython.rlib.rarithmetic import ovfcheck, string_to_int
from rpython.rlib.rbigint import rbigint
from prolog.interpreter.continuation import Engine
from prolog.interpreter.module import Module
from prolog.interpreter import error
from prolog.interpreter.lexer import UnicodeLexer
from rpython.rlib import rutf8

basic_rules = [
    Rule('query', [['toplevel_op_expr', '.', 'EOF']]),
    Rule('fact', [['toplevel_op_expr', '.']]),
    Rule('complexterm', [['ATOM', '(', 'toplevel_op_expr', ')'], ['expr']]),
    Rule('expr',
         [['VAR'],
          ['NUMBER'],
          ['+', 'NUMBER'],
          ['-', 'NUMBER'],
          ['FLOAT'],
          ['+', 'FLOAT'],
          ['-', 'FLOAT'],
          ['ATOM'],
          ['STRING'],
          ['(', 'toplevel_op_expr', ')'],
          ['{', 'toplevel_op_expr', '}'],
          ['listexpr'],
          ]),
    Rule('listexpr', [['[', 'listbody', ']']]),
    Rule('listbody',
         [['toplevel_op_expr', '|', 'toplevel_op_expr'],
          ['toplevel_op_expr']])
    ]

# x: term with priority lower than f
# y: term with priority lower or equal than f
# possible types: xf yf xfx xfy yfx yfy fy fx
# priorities: A > B
#
# binaryops
# (1)  xfx:  A -> B f B | B
# (2)  xfy:  A -> B f A | B
# (3)  yfx:  A -> A f B | B
# (4)  yfy:  A -> A f A | B
#
# unaryops
# (5)  fx:   A -> f A | B
# (6)  fy:   A -> f B | B
# (7)  xf:   A -> B f | B
# (8)  yf:   A -> A f | B

def make_default_operations():
    operations = [
         (1200, [("xfx", ["-->", ":-"]),
                 ("fx",  [":-", "?-"])]),
         (1150, [("fx",  ["meta_predicate"])]),
         (1100, [("xfy", [";"])]),
         (1050, [("xfy", ["->"]),
                 ("fx",  ["block"])]), 
         (1000, [("xfy", [","])]),
         (900,  [("fy",  ["\\+"]),
                 ("fx",  ["~"])]),
         (700,  [("xfx", ["<", "=", "=..", "=@=", "=:=", "=<", "==", "=\=", ">", "?=",
                          ">=", "@<", "@=<", "@>", "@>=", "\=", "\==", "is"])]),
         (600,  [("xfy", [":"])]),
         (500,  [("yfx", ["+", "-", "/\\", "\\/", "xor"]),
                 ( "fx", ["+", "-", "?", "\\"])]),
         (400,  [("yfx", ["*", "/", "//", "<<", ">>", "mod", "rem"])]),
         (200,  [("xfx", ["**"]), ("xfy", ["^"])]),
         ]
    return operations

default_operations = make_default_operations()

import sys
sys.setrecursionlimit(10000)

def make_from_form(form, op, x, y):
    result = []
    for c in form:
        if c == 'x':
            result.append(x)
        if c == 'y':
            result.append(y)
        if c == 'f':
            result.append(op)
    return result

def make_expansion(y, x, allops):
    expansions = []
    for form, ops in allops:
        for op in ops:
            expansion = make_from_form(form, op, x, y)
            expansions.append(expansion)
    expansions.append([x])
    return expansions

def eliminate_immediate_left_recursion(symbol, expansions):
    newsymbol = "extra%s" % (symbol, )
    newexpansions = []
    with_recursion = [expansion for expansion in expansions
                          if expansion[0] == symbol]
    without_recursion = [expansion for expansion in expansions
                              if expansion[0] != symbol]
    expansions = [expansion + [newsymbol] for expansion in without_recursion]
    newexpansions = [expansion[1:] + [newsymbol]
                         for expansion in with_recursion]
    newexpansions.append([])
    return expansions, newexpansions, newsymbol

def make_all_rules(standard_rules, operations=None):
    if operations is None:
        operations = default_operations
    all_rules = standard_rules[:]
    for i in range(len(operations)):
        precedence, allops = operations[i]
        if i == 0:
            y = "toplevel_op_expr"
        else:
            y = "expr%s" % (precedence, )
        if i != len(operations) - 1:
            x = "expr%s" % (operations[i + 1][0], )
        else:
            x = "complexterm"
        expansions = make_expansion(y, x, allops)
        tup = eliminate_immediate_left_recursion(y, expansions)
        expansions, extra_expansions, extra_symbol = tup
        all_rules.append(Rule(extra_symbol, extra_expansions))
        all_rules.append(Rule(y, expansions))
    return all_rules

class PrologParseTable(LazyParseTable):
    def terminal_equality(self, symbol, input):
        if input.name == "ATOM":
            return symbol == "ATOM" or symbol == input.source
        return symbol == input.name
    def match_symbol(self, i, symbol):
        return LazyParseTable.match_symbol(self, i, symbol)

class PrologPackratParser(PackratParser):
    def __init__(self, rules, startsymbol):
        PackratParser.__init__(self, rules, startsymbol, PrologParseTable,
                               check_for_left_recursion=False)

def make_all():
    real_rules = make_all_rules(basic_rules)
    return (UnicodeLexer(), PrologPackratParser(real_rules, "fact"),
            PrologPackratParser(real_rules, "query"), basic_rules)

def make_parser_at_runtime(operations):
    real_rules = make_all_rules(basic_rules, operations)
    parser_fact = PrologPackratParser(real_rules, "fact")
    return parser_fact

def _dummyfunc(arg, tree, source_string, file_name):
    return parser_fact

def parse_file(s, parser=None, callback=_dummyfunc, arg=None, file_name=None):
    if file_name is None:
        file_name = "<unknown>" # for error messages only
    try:
        return _parse_file(s, parser, callback, arg, file_name)
    except ParseError, exc:
        message = exc.nice_error_message(file_name, s)
        lineno = exc.source_pos.lineno
    except LexerError, exc:
        message = exc.nice_error_message(file_name)
        lineno = exc.source_pos.lineno
    raise error.PrologParseError(file_name, lineno, message)


def _parse_file(s, parser, callback, arg, file_name):
    tokens = lexer.tokenize(s)
    lines = []
    line = []
    for tok in tokens:
        line.append(tok)
        if tok.name== ".":
            lines.append(line)
            line = []
    if line:
        pos = tokens[-1].source_pos
        raise ParseError(pos, ErrorInformation(len(tokens) - 1, ["."]))
    if parser is None:
        parser = parser_fact
    trees = []
    for line in lines:
        tree = parser.parse(line, lazy=False)
        callback(arg, tree, s, file_name)
        trees.append(tree)
    return trees

def parse_query(s):
    tokens = lexer.tokenize(s, eof=True)
    s = parser_query.parse(tokens, lazy=False)

def parse_query_term(s):
    return get_query_and_vars(s)[0]

def get_query_and_vars(s):
    tokens = lexer.tokenize(s, eof=True)
    s = parser_query.parse(tokens, lazy=False)
    builder = TermBuilder()
    query = builder.build_query(s)
    return query, builder.varname_to_var

class OrderTransformer(object):
    def transform(self, node):
        if isinstance(node, Symbol):
            return node
        children = [c for c in node.children
                        if isinstance(c, Symbol) or (
                            isinstance(c, Nonterminal) and len(c.children))]
        if isinstance(node, Nonterminal):
            if len(children) == 1:
                return Nonterminal(
                    node.symbol, [self.transform(children[0])])
            if len(children) == 2 or len(children) == 3:
                left = children[-2]
                right = children[-1]
                if (isinstance(right, Nonterminal) and
                    right.symbol.startswith("extraexpr")):
                    if len(children) == 2:
                        leftreplacement = self.transform(left)
                    else:
                        leftreplacement = Nonterminal(
                            node.symbol,
                            [self.transform(children[0]),
                             self.transform(left)])
                    children = [leftreplacement,
                                self.transform(right.children[0]),
                                self.transform(right.children[1])]

                    newnode = Nonterminal(node.symbol, children)
                    return self.transform_extra(right, newnode)
            children = [self.transform(child) for child in children]
            return Nonterminal(node.symbol, children)

    def transform_extra(self, extranode, child):
        children = [c for c in extranode.children
                        if isinstance(c, Symbol) or (
                            isinstance(c, Nonterminal) and len(c.children))]
        symbol = extranode.symbol[5:]
        if len(children) == 2:
            return child
        right = children[2]
        assert isinstance(right, Nonterminal)
        children = [child,
                    self.transform(right.children[0]),
                    self.transform(right.children[1])]
        newnode = Nonterminal(symbol, children)
        return self.transform_extra(right, newnode)

class TermBuilder(RPythonVisitor):

    def __init__(self):
        self.varname_to_var = {}

    def build(self, s):
        "NOT_RPYTHON"
        if isinstance(s, list):
            return self.build_many(s)
        return self.build_query(s)

    def build_many(self, trees):
        ot = OrderTransformer()
        facts = []
        for tree in trees:
            s = ot.transform(tree)
            facts.append(self.build_fact(s))
        return facts

    def build_query(self, s):
        ot = OrderTransformer()
        s = ot.transform(s)
        return self.visit(s.children[0])

    def build_fact(self, node):
        self.varname_to_var = {}
        return self.visit(node.children[0])

    def visit(self, node):
        node = self.find_first_interesting(node)
        return self.dispatch(node)

    def general_nonterminal_visit(self, node):
        from prolog.interpreter.term import Callable, Number, Float, BigInt
        children = []
        name = ""
        for child in node.children:
            if isinstance(child, Symbol):
                name = self.general_symbol_visit(child).name()            
            else:
                children.append(child)
        children = [self.visit(child) for child in children]
        if len(children) == 1 and (name == "-" or name == "+"):
            if name == "-":
                factor = -1
            else:
                factor = 1
            child = children[0]
            if isinstance(child, Number):
                return Number(factor * child.num)
            if isinstance(child, Float):
                return Float(factor * child.floatval)
            if isinstance(child, BigInt):
                return BigInt(rbigint.fromint(factor).mul(child.value))
        return Callable.build(name, children)

    def build_list(self, node):
        result = []
        while node is not None:
            node = self._build_list(node, result)
        return result

    def _build_list(self, node, result):
        node = self.find_first_interesting(node)
        if isinstance(node, Nonterminal):
            child = node.children[1]
            if (isinstance(child, Symbol) and
                node.children[1].additional_info == ","):
                element = self.visit(node.children[0])
                result.append(element)
                return node.children[2]
        result.append(self.visit(node))

    def find_first_interesting(self, node):
        if isinstance(node, Nonterminal) and len(node.children) == 1:
            return self.find_first_interesting(node.children[0])
        return node

    def general_symbol_visit(self, node):
        from prolog.interpreter.term import Callable
        if node.additional_info.startswith("'"):
            end = len(node.additional_info) - 1
            assert end >= 0
            name = unescape(node.additional_info[1:end])
        else:
            name = node.additional_info
        return Callable.build(name)

    def visit_VAR(self, node):
        from prolog.interpreter.term import BindingVar
        varname = node.additional_info
        if varname == "_":
            return BindingVar()
        if varname in self.varname_to_var:
            return self.varname_to_var[varname]
        res = BindingVar()
        self.varname_to_var[varname] = res
        return res

    def visit_NUMBER(self, node):
        from prolog.interpreter.term import Number, BigInt
        s = node.additional_info
        if s.startswith("0'"):
            char = unescape(s[2:])
            if rutf8.codepoints_in_utf8(char) != 1:
                error.throw_syntax_error("character_code")
            return Number(rutf8.codepoint_at_pos(char, 0))
        try:
            intval = string_to_int(s)
        except ParseStringOverflowError: # overflow
            return BigInt(rbigint.fromdecimalstr(s))
        return Number(intval)

    def visit_FLOAT(self, node):
        from prolog.interpreter.term import Float
        s = node.additional_info
        try:
            value = float(s)
        except OverflowError:
            error.throw_syntax_error("float_overflow")
        if math.isinf(value):
            error.throw_syntax_error("float_overflow")
        return Float(value)

    def visit_STRING(self, node):
        from prolog.interpreter import helper
        from prolog.interpreter.term import Callable, Number
        info = node.additional_info
        end = len(info) - 1
        assert end >= 1
        s = unescape(info[1:end], '"')
        l = [Number(c) for c in rutf8.Utf8StringIterator(s)]
        return helper.wrap_list(l)

    def visit_complexterm(self, node):
        from prolog.interpreter.term import Callable
        name = self.general_symbol_visit(node.children[0]).name()
        children = self.build_list(node.children[2])
        return Callable.build(name, children[:])

    def visit_expr(self, node):
        from prolog.interpreter.term import Number, Float, BigInt
        additional_info = node.children[0].additional_info
        result = self.visit(node.children[1])
        if additional_info == '-':
            if isinstance(result, Number):
                return Number(-result.num)
            elif isinstance(result, Float):
                return Float(-result.floatval)
        elif additional_info == "{":
            from prolog.interpreter.term import Callable
            return Callable.build("{}", [result])
        return result

    def visit_listexpr(self, node):
        from prolog.interpreter.term import Callable
        node = node.children[1]
        if len(node.children) == 1:
            l = self.build_list(node)
            start = Callable.build("[]")
        else:
            l = self.build_list(node.children[0])
            start = self.visit(node.children[2])
        l.reverse()
        curr = start
        for elt in l:
            curr = Callable.build(".", [elt, curr])
        return curr


ESCAPES = {
    "\\a": "\a",
    "\\b": "\b",
    "\\f": "\f",
    "\\n": "\n",
    "\\r": "\r",
    "\\t": "\t",
    "\\v": "\v",
    "\\\\":  "\\"
}


def unescape(s, quote="'"):
    result = []
    i = 0
    while i < len(s):
        c = s[i]
        i += 1
        if c == quote and i < len(s) and s[i] == quote:
            result.append(c)
            i += 1
        elif c != "\\":
            result.append(c)
        else:
            if i == len(s):
                error.throw_syntax_error("character_escape")
            c = s[i]
            i += 1
            if c in 'uU':
                count = 4 if c == 'u' else 8
                if i + count > len(s):
                    error.throw_syntax_error("character_escape")
                value = 0
                for j in range(count):
                    digit = s[i + j].lower()
                    if digit not in '0123456789abcdef':
                        error.throw_syntax_error("character_escape")
                    value = value * 16 + '0123456789abcdef'.find(digit)
                i += count
                try:
                    result.append(rutf8.unichr_as_utf8(value))
                except rutf8.OutOfRange:
                    error.throw_syntax_error("character_code")
            elif c == 'x' or '0' <= c <= '7':
                base = 16 if c == 'x' else 8
                value = 0 if c == 'x' else ord(c) - 48
                digits = 0 if c == 'x' else 1
                while i < len(s) and s[i] != "\\":
                    digit = '0123456789abcdef'.find(s[i].lower())
                    if digit < 0 or digit >= base or value > 0x10ffff:
                        error.throw_syntax_error("character_escape")
                    value = value * base + digit
                    digits += 1
                    i += 1
                if i == len(s) or digits == 0:
                    error.throw_syntax_error("character_escape")
                i += 1
                try:
                    result.append(rutf8.unichr_as_utf8(value))
                except rutf8.OutOfRange:
                    error.throw_syntax_error("character_code")
            elif c == "\n":
                pass
            elif c in "'\"":
                result.append(c)
            elif "\\" + c in ESCAPES:
                result.append(ESCAPES["\\" + c])
            else:
                error.throw_syntax_error("character_escape")
    return "".join(result)


def get_engine(source, create_files=False, load_system=False, **modules):
    from prolog.interpreter.continuation import Engine
    from prolog.interpreter.test.tool import create_file, delete_file
    e = Engine(load_system)
    for name, module in modules.iteritems():
        if create_files:
            create_file(name, module)
        else:
            e.runstring(module)
    try:
        e.modulewrapper.current_module = e.modulewrapper.user_module
        e.runstring(source)
    finally:
        if create_files:
            for name in modules.keys():
                delete_file(name)
    return e

# generated code between this line and its other occurence

parser_fact = PrologPackratParser([Rule('query', [['toplevel_op_expr', '.', 'EOF']]),
  Rule('fact', [['toplevel_op_expr', '.']]),
  Rule('complexterm', [['ATOM', '(', 'toplevel_op_expr', ')'], ['expr']]),
  Rule('expr', [['VAR'], ['NUMBER'], ['+', 'NUMBER'], ['-', 'NUMBER'], ['FLOAT'], ['+', 'FLOAT'], ['-', 'FLOAT'], ['ATOM'], ['STRING'], ['(', 'toplevel_op_expr', ')'], ['{', 'toplevel_op_expr', '}'], ['listexpr']]),
  Rule('listexpr', [['[', 'listbody', ']']]),
  Rule('listbody', [['toplevel_op_expr', '|', 'toplevel_op_expr'], ['toplevel_op_expr']]),
  Rule('extratoplevel_op_expr', [[]]),
  Rule('toplevel_op_expr', [['expr1150', '-->', 'expr1150', 'extratoplevel_op_expr'], ['expr1150', ':-', 'expr1150', 'extratoplevel_op_expr'], [':-', 'expr1150', 'extratoplevel_op_expr'], ['?-', 'expr1150', 'extratoplevel_op_expr'], ['expr1150', 'extratoplevel_op_expr']]),
  Rule('extraexpr1150', [[]]),
  Rule('expr1150', [['meta_predicate', 'expr1100', 'extraexpr1150'], ['expr1100', 'extraexpr1150']]),
  Rule('extraexpr1100', [[]]),
  Rule('expr1100', [['expr1050', ';', 'expr1100', 'extraexpr1100'], ['expr1050', 'extraexpr1100']]),
  Rule('extraexpr1050', [[]]),
  Rule('expr1050', [['expr1000', '->', 'expr1050', 'extraexpr1050'], ['block', 'expr1000', 'extraexpr1050'], ['expr1000', 'extraexpr1050']]),
  Rule('extraexpr1000', [[]]),
  Rule('expr1000', [['expr900', ',', 'expr1000', 'extraexpr1000'], ['expr900', 'extraexpr1000']]),
  Rule('extraexpr900', [[]]),
  Rule('expr900', [['\\+', 'expr900', 'extraexpr900'], ['~', 'expr700', 'extraexpr900'], ['expr700', 'extraexpr900']]),
  Rule('extraexpr700', [[]]),
  Rule('expr700', [['expr600', '<', 'expr600', 'extraexpr700'], ['expr600', '=', 'expr600', 'extraexpr700'], ['expr600', '=..', 'expr600', 'extraexpr700'], ['expr600', '=@=', 'expr600', 'extraexpr700'], ['expr600', '=:=', 'expr600', 'extraexpr700'], ['expr600', '=<', 'expr600', 'extraexpr700'], ['expr600', '==', 'expr600', 'extraexpr700'], ['expr600', '=\\=', 'expr600', 'extraexpr700'], ['expr600', '>', 'expr600', 'extraexpr700'], ['expr600', '?=', 'expr600', 'extraexpr700'], ['expr600', '>=', 'expr600', 'extraexpr700'], ['expr600', '@<', 'expr600', 'extraexpr700'], ['expr600', '@=<', 'expr600', 'extraexpr700'], ['expr600', '@>', 'expr600', 'extraexpr700'], ['expr600', '@>=', 'expr600', 'extraexpr700'], ['expr600', '\\=', 'expr600', 'extraexpr700'], ['expr600', '\\==', 'expr600', 'extraexpr700'], ['expr600', 'is', 'expr600', 'extraexpr700'], ['expr600', 'extraexpr700']]),
  Rule('extraexpr600', [[]]),
  Rule('expr600', [['expr500', ':', 'expr600', 'extraexpr600'], ['expr500', 'extraexpr600']]),
  Rule('extraexpr500', [['+', 'expr400', 'extraexpr500'], ['-', 'expr400', 'extraexpr500'], ['/\\', 'expr400', 'extraexpr500'], ['\\/', 'expr400', 'extraexpr500'], ['xor', 'expr400', 'extraexpr500'], []]),
  Rule('expr500', [['+', 'expr400', 'extraexpr500'], ['-', 'expr400', 'extraexpr500'], ['?', 'expr400', 'extraexpr500'], ['\\', 'expr400', 'extraexpr500'], ['expr400', 'extraexpr500']]),
  Rule('extraexpr400', [['*', 'expr200', 'extraexpr400'], ['/', 'expr200', 'extraexpr400'], ['//', 'expr200', 'extraexpr400'], ['<<', 'expr200', 'extraexpr400'], ['>>', 'expr200', 'extraexpr400'], ['mod', 'expr200', 'extraexpr400'], ['rem', 'expr200', 'extraexpr400'], []]),
  Rule('expr400', [['expr200', 'extraexpr400']]),
  Rule('extraexpr200', [[]]),
  Rule('expr200', [['complexterm', '**', 'complexterm', 'extraexpr200'], ['complexterm', '^', 'expr200', 'extraexpr200'], ['complexterm', 'extraexpr200']])],
 'fact')
parser_query = PrologPackratParser([Rule('query', [['toplevel_op_expr', '.', 'EOF']]),
  Rule('fact', [['toplevel_op_expr', '.']]),
  Rule('complexterm', [['ATOM', '(', 'toplevel_op_expr', ')'], ['expr']]),
  Rule('expr', [['VAR'], ['NUMBER'], ['+', 'NUMBER'], ['-', 'NUMBER'], ['FLOAT'], ['+', 'FLOAT'], ['-', 'FLOAT'], ['ATOM'], ['STRING'], ['(', 'toplevel_op_expr', ')'], ['{', 'toplevel_op_expr', '}'], ['listexpr']]),
  Rule('listexpr', [['[', 'listbody', ']']]),
  Rule('listbody', [['toplevel_op_expr', '|', 'toplevel_op_expr'], ['toplevel_op_expr']]),
  Rule('extratoplevel_op_expr', [[]]),
  Rule('toplevel_op_expr', [['expr1150', '-->', 'expr1150', 'extratoplevel_op_expr'], ['expr1150', ':-', 'expr1150', 'extratoplevel_op_expr'], [':-', 'expr1150', 'extratoplevel_op_expr'], ['?-', 'expr1150', 'extratoplevel_op_expr'], ['expr1150', 'extratoplevel_op_expr']]),
  Rule('extraexpr1150', [[]]),
  Rule('expr1150', [['meta_predicate', 'expr1100', 'extraexpr1150'], ['expr1100', 'extraexpr1150']]),
  Rule('extraexpr1100', [[]]),
  Rule('expr1100', [['expr1050', ';', 'expr1100', 'extraexpr1100'], ['expr1050', 'extraexpr1100']]),
  Rule('extraexpr1050', [[]]),
  Rule('expr1050', [['expr1000', '->', 'expr1050', 'extraexpr1050'], ['block', 'expr1000', 'extraexpr1050'], ['expr1000', 'extraexpr1050']]),
  Rule('extraexpr1000', [[]]),
  Rule('expr1000', [['expr900', ',', 'expr1000', 'extraexpr1000'], ['expr900', 'extraexpr1000']]),
  Rule('extraexpr900', [[]]),
  Rule('expr900', [['\\+', 'expr900', 'extraexpr900'], ['~', 'expr700', 'extraexpr900'], ['expr700', 'extraexpr900']]),
  Rule('extraexpr700', [[]]),
  Rule('expr700', [['expr600', '<', 'expr600', 'extraexpr700'], ['expr600', '=', 'expr600', 'extraexpr700'], ['expr600', '=..', 'expr600', 'extraexpr700'], ['expr600', '=@=', 'expr600', 'extraexpr700'], ['expr600', '=:=', 'expr600', 'extraexpr700'], ['expr600', '=<', 'expr600', 'extraexpr700'], ['expr600', '==', 'expr600', 'extraexpr700'], ['expr600', '=\\=', 'expr600', 'extraexpr700'], ['expr600', '>', 'expr600', 'extraexpr700'], ['expr600', '?=', 'expr600', 'extraexpr700'], ['expr600', '>=', 'expr600', 'extraexpr700'], ['expr600', '@<', 'expr600', 'extraexpr700'], ['expr600', '@=<', 'expr600', 'extraexpr700'], ['expr600', '@>', 'expr600', 'extraexpr700'], ['expr600', '@>=', 'expr600', 'extraexpr700'], ['expr600', '\\=', 'expr600', 'extraexpr700'], ['expr600', '\\==', 'expr600', 'extraexpr700'], ['expr600', 'is', 'expr600', 'extraexpr700'], ['expr600', 'extraexpr700']]),
  Rule('extraexpr600', [[]]),
  Rule('expr600', [['expr500', ':', 'expr600', 'extraexpr600'], ['expr500', 'extraexpr600']]),
  Rule('extraexpr500', [['+', 'expr400', 'extraexpr500'], ['-', 'expr400', 'extraexpr500'], ['/\\', 'expr400', 'extraexpr500'], ['\\/', 'expr400', 'extraexpr500'], ['xor', 'expr400', 'extraexpr500'], []]),
  Rule('expr500', [['+', 'expr400', 'extraexpr500'], ['-', 'expr400', 'extraexpr500'], ['?', 'expr400', 'extraexpr500'], ['\\', 'expr400', 'extraexpr500'], ['expr400', 'extraexpr500']]),
  Rule('extraexpr400', [['*', 'expr200', 'extraexpr400'], ['/', 'expr200', 'extraexpr400'], ['//', 'expr200', 'extraexpr400'], ['<<', 'expr200', 'extraexpr400'], ['>>', 'expr200', 'extraexpr400'], ['mod', 'expr200', 'extraexpr400'], ['rem', 'expr200', 'extraexpr400'], []]),
  Rule('expr400', [['expr200', 'extraexpr400']]),
  Rule('extraexpr200', [[]]),
  Rule('expr200', [['complexterm', '**', 'complexterm', 'extraexpr200'], ['complexterm', '^', 'expr200', 'extraexpr200'], ['complexterm', 'extraexpr200']])],
 'query')
# generated code between this line and its other occurence

lexer = UnicodeLexer()

if __name__ == '__main__':
    f = py.path.local(__file__)
    oldcontent = f.read()
    s = "# GENERATED CODE BETWEEN THIS LINE AND ITS OTHER OCCURENCE\n".lower()
    pre, gen, after = oldcontent.split(s)

    lexer, parser_fact, parser_query, basic_rules = make_all()
    newcontent = ("%s%s\nparser_fact = %r\nparser_query = %r\n%s\n"
                  "\n%s%s") % (
            pre, s, parser_fact, parser_query, '',
            s, after)
    print newcontent
    f.write(newcontent)
