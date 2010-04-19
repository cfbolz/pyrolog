import py
from pypy.rlib.parsing.ebnfparse import parse_ebnf
from pypy.rlib.parsing.regexparse import parse_regex
from pypy.rlib.parsing.lexer import Lexer, DummyLexer
from pypy.rlib.parsing.deterministic import DFA
from pypy.rlib.parsing.tree import Nonterminal, Symbol, RPythonVisitor
from pypy.rlib.parsing.parsing import PackratParser, LazyParseTable, Rule
from pypy.rlib.parsing.regex import StringExpression

def make_regexes():
    regexs = [
        ("VAR", parse_regex("[A-Z_]([a-zA-Z0-9]|_)*|_")),
        ("NUMBER", parse_regex("(0|[1-9][0-9]*)(\.[0-9]+)?")),
        ("IGNORE", parse_regex(
            "[ \\n\\t]|(/\\*[^\\*]*(\\*[^/][^\\*]*)*\\*/)|(%[^\\n]*)")),
        ("ATOM", parse_regex("([a-z]([a-zA-Z0-9]|_)*)|('[^']*')|\[\]|!|\+|\-|#|&")),
        ("(", parse_regex("\(")),
        (")", parse_regex("\)")),
        ("[", parse_regex("\[")),
        ("]", parse_regex("\]")),
        ("{", parse_regex("\{")),
        ("}", parse_regex("\}")),
        (".", parse_regex("\.")),
        ("|", parse_regex("\|")),
    ]
    return zip(*regexs)

basic_rules = [
    Rule('query', [['toplevel_op_expr', '.', 'EOF']]),
    Rule('fact', [['toplevel_op_expr', '.']]),
    Rule('complexterm', [['ATOM', '(', 'toplevel_op_expr', ')'],
                         ['{', '}'],
                         ['{', 'toplevel_op_expr', '}'],
                         ['expr']]),
    Rule('expr',
         [['VAR'],
          ['NUMBER'],
          ['+', 'NUMBER'],
          ['-', 'NUMBER'],
          ['ATOM'],
          ['(', 'toplevel_op_expr', ')'],
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
         (1150, [("fx", ["dynamic", "discontiguous", "initialization",
                         "meta_predicate", "module_transparent", "multifile"])]),
         (1100, [("xfy", [";"])]),
         (1050, [("xfy", ["->"])]),
         (1000, [("xfy", [","])]),
         (900,  [("fy",  ["\\+"]),
                 ("fx",  ["~"])]),
         (700,  [("xfx", ["<", "=", "=..", "=@=", "=:=", "=<", "==", "=\=", ">",
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

def add_necessary_regexs(regexs, names, operations=None):
    if operations is None:
        operations = default_operations
    regexs = regexs[:]
    names = names[:]
    for precedence, allops in operations:
        for form, ops in allops:
            for op in ops:
                regexs.insert(-1, StringExpression(op))
                names.insert(-1, "ATOM")
    return regexs, names

class PrologParseTable(LazyParseTable):
    def terminal_equality(self, symbol, input):
        if input.name == "ATOM":
            return symbol == "ATOM" or symbol == input.source
        return symbol == input.name
class PrologPackratParser(PackratParser):
    def __init__(self, rules, startsymbol):
        PackratParser.__init__(self, rules, startsymbol, PrologParseTable,
                               check_for_left_recursion=False)

def make_basic_rules():
    names, regexs = make_regexes()
    return basic_rules, names, regexs

def make_parser(basic_rules, names, regexs):
    real_rules = make_all_rules(basic_rules)
#    for r in real_rules:
#        print r
    regexs, names = add_necessary_regexs(list(regexs), list(names))
    lexer = Lexer(regexs, names, ignore=["IGNORE"])
    parser_fact = PrologPackratParser(real_rules, "fact")
    parser_query = PrologPackratParser(real_rules, "query")
    return lexer, parser_fact, parser_query, basic_rules

def make_all():
    return make_parser(*make_basic_rules())

def make_parser_at_runtime(operations):
    real_rules = make_all_rules(basic_rules, operations)
    parser_fact = PrologPackratParser(real_rules, "fact")
    return parser_fact

def _dummyfunc(arg, tree):
    return parser_fact

def parse_file(s, parser=None, callback=_dummyfunc, arg=None):
    tokens = lexer.tokenize(s)
    lines = []
    line = []
    for tok in tokens:
        line.append(tok)
        if tok.name== ".":
            lines.append(line)
            line = []
    if parser is None:
        parser = parser_fact
    trees = []
    for line in lines:
        tree = parser.parse(line, lazy=False)
        if callback is not None:
            # XXX ugh
            parser = callback(arg, tree)
            if parser is None:
                parser = parser_fact
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
    query = builder.build(s)
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
        from prolog.interpreter.term import Callable, Number, Float
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
        from prolog.interpreter.term import Var
        varname = node.additional_info
        if varname == "_":
            return Var()
        if varname in self.varname_to_var:
            return self.varname_to_var[varname]
        res = Var()
        self.varname_to_var[varname] = res
        return res

    def visit_NUMBER(self, node):
        from prolog.interpreter.term import Number, Float
        s = node.additional_info
        try:
            return Number(int(s))
        except ValueError:
            return Float(float(s))

    def visit_complexterm(self, node):
        from prolog.interpreter.term import Callable
        if node.children[0].additional_info == "{":
            if len(node.children) == 2:
                return Callable.build('{}')
            name = '{}'
            childrenindex = 1
        else:
            name = self.general_symbol_visit(node.children[0]).name()
            childrenindex = 2
        children = self.build_list(node.children[childrenindex])
        return Callable.build(name, children[:])

    def visit_expr(self, node):
        from prolog.interpreter.term import Number, Float
        if node.children[0].additional_info == '-':
            result = self.visit(node.children[1])
            if isinstance(result, Number):
                return Number(-result.num)
            elif isinstance(result, Float):
                return Float(-result.floatval)
        return self.visit(node.children[1])

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


def unescape(s):
    # XXX support \'
    if "\\" not in s:
        return s
    result = []
    i = 0
    escape = False
    while i < len(s):
        c = s[i]
        if escape:
            escape = False
            f = "\\" + c
            if f in ESCAPES:
                result.append(ESCAPES[f])
            else:
                result.append(c)
        elif c == "\\":
            escape = True
        else:
            result.append(c)
        i += 1
    return "".join(result)


# generated code between this line and its other occurence

parser_fact = PrologPackratParser([Rule('query', [['toplevel_op_expr', '.', 'EOF']]),
  Rule('fact', [['toplevel_op_expr', '.']]),
  Rule('complexterm', [['ATOM', '(', 'toplevel_op_expr', ')'], ['{', '}'], ['{', 'toplevel_op_expr', '}'], ['expr']]),
  Rule('expr', [['VAR'], ['NUMBER'], ['+', 'NUMBER'], ['-', 'NUMBER'], ['ATOM'], ['(', 'toplevel_op_expr', ')'], ['listexpr']]),
  Rule('listexpr', [['[', 'listbody', ']']]),
  Rule('listbody', [['toplevel_op_expr', '|', 'toplevel_op_expr'], ['toplevel_op_expr']]),
  Rule('extratoplevel_op_expr', [[]]),
  Rule('toplevel_op_expr', [['expr1150', '-->', 'expr1150', 'extratoplevel_op_expr'], ['expr1150', ':-', 'expr1150', 'extratoplevel_op_expr'], [':-', 'expr1150', 'extratoplevel_op_expr'], ['?-', 'expr1150', 'extratoplevel_op_expr'], ['expr1150', 'extratoplevel_op_expr']]),
  Rule('extraexpr1150', [[]]),
  Rule('expr1150', [['dynamic', 'expr1100', 'extraexpr1150'], ['discontiguous', 'expr1100', 'extraexpr1150'], ['initialization', 'expr1100', 'extraexpr1150'], ['meta_predicate', 'expr1100', 'extraexpr1150'], ['module_transparent', 'expr1100', 'extraexpr1150'], ['multifile', 'expr1100', 'extraexpr1150'], ['expr1100', 'extraexpr1150']]),
  Rule('extraexpr1100', [[]]),
  Rule('expr1100', [['expr1050', ';', 'expr1100', 'extraexpr1100'], ['expr1050', 'extraexpr1100']]),
  Rule('extraexpr1050', [[]]),
  Rule('expr1050', [['expr1000', '->', 'expr1050', 'extraexpr1050'], ['expr1000', 'extraexpr1050']]),
  Rule('extraexpr1000', [[]]),
  Rule('expr1000', [['expr900', ',', 'expr1000', 'extraexpr1000'], ['expr900', 'extraexpr1000']]),
  Rule('extraexpr900', [[]]),
  Rule('expr900', [['\\+', 'expr900', 'extraexpr900'], ['~', 'expr700', 'extraexpr900'], ['expr700', 'extraexpr900']]),
  Rule('extraexpr700', [[]]),
  Rule('expr700', [['expr600', '<', 'expr600', 'extraexpr700'], ['expr600', '=', 'expr600', 'extraexpr700'], ['expr600', '=..', 'expr600', 'extraexpr700'], ['expr600', '=@=', 'expr600', 'extraexpr700'], ['expr600', '=:=', 'expr600', 'extraexpr700'], ['expr600', '=<', 'expr600', 'extraexpr700'], ['expr600', '==', 'expr600', 'extraexpr700'], ['expr600', '=\\=', 'expr600', 'extraexpr700'], ['expr600', '>', 'expr600', 'extraexpr700'], ['expr600', '>=', 'expr600', 'extraexpr700'], ['expr600', '@<', 'expr600', 'extraexpr700'], ['expr600', '@=<', 'expr600', 'extraexpr700'], ['expr600', '@>', 'expr600', 'extraexpr700'], ['expr600', '@>=', 'expr600', 'extraexpr700'], ['expr600', '\\=', 'expr600', 'extraexpr700'], ['expr600', '\\==', 'expr600', 'extraexpr700'], ['expr600', 'is', 'expr600', 'extraexpr700'], ['expr600', 'extraexpr700']]),
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
  Rule('complexterm', [['ATOM', '(', 'toplevel_op_expr', ')'], ['{', '}'], ['{', 'toplevel_op_expr', '}'], ['expr']]),
  Rule('expr', [['VAR'], ['NUMBER'], ['+', 'NUMBER'], ['-', 'NUMBER'], ['ATOM'], ['(', 'toplevel_op_expr', ')'], ['listexpr']]),
  Rule('listexpr', [['[', 'listbody', ']']]),
  Rule('listbody', [['toplevel_op_expr', '|', 'toplevel_op_expr'], ['toplevel_op_expr']]),
  Rule('extratoplevel_op_expr', [[]]),
  Rule('toplevel_op_expr', [['expr1150', '-->', 'expr1150', 'extratoplevel_op_expr'], ['expr1150', ':-', 'expr1150', 'extratoplevel_op_expr'], [':-', 'expr1150', 'extratoplevel_op_expr'], ['?-', 'expr1150', 'extratoplevel_op_expr'], ['expr1150', 'extratoplevel_op_expr']]),
  Rule('extraexpr1150', [[]]),
  Rule('expr1150', [['dynamic', 'expr1100', 'extraexpr1150'], ['discontiguous', 'expr1100', 'extraexpr1150'], ['initialization', 'expr1100', 'extraexpr1150'], ['meta_predicate', 'expr1100', 'extraexpr1150'], ['module_transparent', 'expr1100', 'extraexpr1150'], ['multifile', 'expr1100', 'extraexpr1150'], ['expr1100', 'extraexpr1150']]),
  Rule('extraexpr1100', [[]]),
  Rule('expr1100', [['expr1050', ';', 'expr1100', 'extraexpr1100'], ['expr1050', 'extraexpr1100']]),
  Rule('extraexpr1050', [[]]),
  Rule('expr1050', [['expr1000', '->', 'expr1050', 'extraexpr1050'], ['expr1000', 'extraexpr1050']]),
  Rule('extraexpr1000', [[]]),
  Rule('expr1000', [['expr900', ',', 'expr1000', 'extraexpr1000'], ['expr900', 'extraexpr1000']]),
  Rule('extraexpr900', [[]]),
  Rule('expr900', [['\\+', 'expr900', 'extraexpr900'], ['~', 'expr700', 'extraexpr900'], ['expr700', 'extraexpr900']]),
  Rule('extraexpr700', [[]]),
  Rule('expr700', [['expr600', '<', 'expr600', 'extraexpr700'], ['expr600', '=', 'expr600', 'extraexpr700'], ['expr600', '=..', 'expr600', 'extraexpr700'], ['expr600', '=@=', 'expr600', 'extraexpr700'], ['expr600', '=:=', 'expr600', 'extraexpr700'], ['expr600', '=<', 'expr600', 'extraexpr700'], ['expr600', '==', 'expr600', 'extraexpr700'], ['expr600', '=\\=', 'expr600', 'extraexpr700'], ['expr600', '>', 'expr600', 'extraexpr700'], ['expr600', '>=', 'expr600', 'extraexpr700'], ['expr600', '@<', 'expr600', 'extraexpr700'], ['expr600', '@=<', 'expr600', 'extraexpr700'], ['expr600', '@>', 'expr600', 'extraexpr700'], ['expr600', '@>=', 'expr600', 'extraexpr700'], ['expr600', '\\=', 'expr600', 'extraexpr700'], ['expr600', '\\==', 'expr600', 'extraexpr700'], ['expr600', 'is', 'expr600', 'extraexpr700'], ['expr600', 'extraexpr700']]),
  Rule('extraexpr600', [[]]),
  Rule('expr600', [['expr500', ':', 'expr600', 'extraexpr600'], ['expr500', 'extraexpr600']]),
  Rule('extraexpr500', [['+', 'expr400', 'extraexpr500'], ['-', 'expr400', 'extraexpr500'], ['/\\', 'expr400', 'extraexpr500'], ['\\/', 'expr400', 'extraexpr500'], ['xor', 'expr400', 'extraexpr500'], []]),
  Rule('expr500', [['+', 'expr400', 'extraexpr500'], ['-', 'expr400', 'extraexpr500'], ['?', 'expr400', 'extraexpr500'], ['\\', 'expr400', 'extraexpr500'], ['expr400', 'extraexpr500']]),
  Rule('extraexpr400', [['*', 'expr200', 'extraexpr400'], ['/', 'expr200', 'extraexpr400'], ['//', 'expr200', 'extraexpr400'], ['<<', 'expr200', 'extraexpr400'], ['>>', 'expr200', 'extraexpr400'], ['mod', 'expr200', 'extraexpr400'], ['rem', 'expr200', 'extraexpr400'], []]),
  Rule('expr400', [['expr200', 'extraexpr400']]),
  Rule('extraexpr200', [[]]),
  Rule('expr200', [['complexterm', '**', 'complexterm', 'extraexpr200'], ['complexterm', '^', 'expr200', 'extraexpr200'], ['complexterm', 'extraexpr200']])],
 'query')
def recognize(runner, i):
    #auto-generated code, don't edit
    assert i >= 0
    input = runner.text
    state = 0
    while 1:
        if state == 0:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 0
                return ~i
            if char == '\t':
                state = 1
            elif char == '\n':
                state = 1
            elif char == ' ':
                state = 1
            elif char == '(':
                state = 2
            elif char == ',':
                state = 3
            elif char == '0':
                state = 4
            elif '1' <= char <= '9':
                state = 5
            elif char == '<':
                state = 6
            elif char == '@':
                state = 7
            elif 'A' <= char <= 'Z':
                state = 8
            elif char == '_':
                state = 8
            elif char == '\\':
                state = 9
            elif char == 'd':
                state = 10
            elif 's' <= char <= 'w':
                state = 11
            elif 'e' <= char <= 'h':
                state = 11
            elif 'n' <= char <= 'q':
                state = 11
            elif 'a' <= char <= 'c':
                state = 11
            elif 'j' <= char <= 'l':
                state = 11
            elif char == 'y':
                state = 11
            elif char == 'z':
                state = 11
            elif char == 'x':
                state = 12
            elif char == '|':
                state = 13
            elif char == '!':
                state = 14
            elif char == '#':
                state = 14
            elif char == '&':
                state = 14
            elif char == "'":
                state = 15
            elif char == '+':
                state = 16
            elif char == '/':
                state = 17
            elif char == ';':
                state = 18
            elif char == '?':
                state = 19
            elif char == '[':
                state = 20
            elif char == '{':
                state = 21
            elif char == '*':
                state = 22
            elif char == '.':
                state = 23
            elif char == ':':
                state = 24
            elif char == '>':
                state = 25
            elif char == '^':
                state = 26
            elif char == 'r':
                state = 27
            elif char == '~':
                state = 28
            elif char == '%':
                state = 29
            elif char == ')':
                state = 30
            elif char == '-':
                state = 31
            elif char == '=':
                state = 32
            elif char == ']':
                state = 33
            elif char == 'i':
                state = 34
            elif char == 'm':
                state = 35
            elif char == '}':
                state = 36
            else:
                break
        if state == 4:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 4
                return i
            if char == '.':
                state = 143
            else:
                break
        if state == 5:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 5
                return i
            if '0' <= char <= '9':
                state = 5
                continue
            elif char == '.':
                state = 143
            else:
                break
        if state == 6:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 6
                return i
            if char == '<':
                state = 142
            else:
                break
        if state == 7:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 7
                return ~i
            if char == '=':
                state = 137
            elif char == '<':
                state = 138
            elif char == '>':
                state = 139
            else:
                break
        if state == 8:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 8
                return i
            if 'A' <= char <= 'Z':
                state = 8
                continue
            elif 'a' <= char <= 'z':
                state = 8
                continue
            elif '0' <= char <= '9':
                state = 8
                continue
            elif char == '_':
                state = 8
                continue
            else:
                break
        if state == 9:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 9
                return i
            if char == '+':
                state = 133
            elif char == '=':
                state = 134
            elif char == '/':
                state = 135
            else:
                break
        if state == 10:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 10
                return i
            if char == 'i':
                state = 115
            elif 'A' <= char <= 'Z':
                state = 11
            elif 'j' <= char <= 'x':
                state = 11
            elif '0' <= char <= '9':
                state = 11
            elif 'a' <= char <= 'h':
                state = 11
            elif char == '_':
                state = 11
            elif char == 'z':
                state = 11
            elif char == 'y':
                state = 116
            else:
                break
        if state == 11:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 11
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 12:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 12
                return i
            if char == 'o':
                state = 113
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'n':
                state = 11
                continue
            elif 'p' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 15:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 15
                return ~i
            if char == "'":
                state = 14
            elif '(' <= char <= '\xff':
                state = 15
                continue
            elif '\x00' <= char <= '&':
                state = 15
                continue
            else:
                break
        if state == 17:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 17
                return i
            if char == '*':
                state = 109
            elif char == '\\':
                state = 110
            elif char == '/':
                state = 111
            else:
                break
        if state == 19:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 19
                return i
            if char == '-':
                state = 108
            else:
                break
        if state == 20:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 20
                return i
            if char == ']':
                state = 14
            else:
                break
        if state == 22:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 22
                return i
            if char == '*':
                state = 107
            else:
                break
        if state == 24:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 24
                return i
            if char == '-':
                state = 106
            else:
                break
        if state == 25:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 25
                return i
            if char == '=':
                state = 104
            elif char == '>':
                state = 105
            else:
                break
        if state == 27:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 27
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'f' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'd':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'e':
                state = 102
            else:
                break
        if state == 29:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 29
                return i
            if '\x0b' <= char <= '\xff':
                state = 29
                continue
            elif '\x00' <= char <= '\t':
                state = 29
                continue
            else:
                break
        if state == 31:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 31
                return i
            if char == '-':
                state = 99
            elif char == '>':
                state = 100
            else:
                break
        if state == 32:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 32
                return i
            if char == '@':
                state = 89
            elif char == '<':
                state = 90
            elif char == '.':
                state = 91
            elif char == ':':
                state = 92
            elif char == '=':
                state = 93
            elif char == '\\':
                state = 94
            else:
                break
        if state == 34:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 34
                return i
            if char == 'n':
                state = 75
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'm':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 't' <= char <= 'z':
                state = 11
                continue
            elif 'o' <= char <= 'r':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 's':
                state = 76
            else:
                break
        if state == 35:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 35
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'f' <= char <= 'n':
                state = 11
                continue
            elif 'p' <= char <= 't':
                state = 11
                continue
            elif 'v' <= char <= 'z':
                state = 11
                continue
            elif 'a' <= char <= 'd':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'e':
                state = 37
            elif char == 'o':
                state = 38
            elif char == 'u':
                state = 39
            else:
                break
        if state == 37:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 37
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 's':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'u' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 't':
                state = 63
            else:
                break
        if state == 38:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 38
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'e' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'c':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'd':
                state = 47
            else:
                break
        if state == 39:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 39
                return i
            if char == 'l':
                state = 40
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'm' <= char <= 'z':
                state = 11
                continue
            elif 'a' <= char <= 'k':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 40:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 40
                return i
            if char == 't':
                state = 41
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 's':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'u' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 41:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 41
                return i
            if char == 'i':
                state = 42
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'j' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'h':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 42:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 42
                return i
            if char == 'f':
                state = 43
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'g' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'e':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 43:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 43
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'j' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'h':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'i':
                state = 44
            else:
                break
        if state == 44:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 44
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'm' <= char <= 'z':
                state = 11
                continue
            elif 'a' <= char <= 'k':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'l':
                state = 45
            else:
                break
        if state == 45:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 45
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'f' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'd':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'e':
                state = 46
            else:
                break
        if state == 46:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 46
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 47:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 47
                return i
            if char == 'u':
                state = 48
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 't':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'v' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 48:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 48
                return i
            if char == 'l':
                state = 49
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'm' <= char <= 'z':
                state = 11
                continue
            elif 'a' <= char <= 'k':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 49:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 49
                return i
            if char == 'e':
                state = 50
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'f' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'd':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 50:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 50
                return i
            if char == '_':
                state = 51
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            else:
                break
        if state == 51:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 51
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 's':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'u' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 't':
                state = 52
            else:
                break
        if state == 52:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 52
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'q':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 's' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'r':
                state = 53
            else:
                break
        if state == 53:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 53
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'b' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'a':
                state = 54
            else:
                break
        if state == 54:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 54
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'm':
                state = 11
                continue
            elif 'o' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'n':
                state = 55
            else:
                break
        if state == 55:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 55
                return i
            if char == 's':
                state = 56
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'r':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 't' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 56:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 56
                return i
            if char == 'p':
                state = 57
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'o':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'q' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 57:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 57
                return i
            if char == 'a':
                state = 58
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'b' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 58:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 58
                return i
            if char == 'r':
                state = 59
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'q':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 's' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 59:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 59
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'f' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'd':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'e':
                state = 60
            else:
                break
        if state == 60:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 60
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'm':
                state = 11
                continue
            elif 'o' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'n':
                state = 61
            else:
                break
        if state == 61:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 61
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 's':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'u' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 't':
                state = 62
            else:
                break
        if state == 62:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 62
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 63:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 63
                return i
            if char == 'a':
                state = 64
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'b' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 64:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 64
                return i
            if char == '_':
                state = 65
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            else:
                break
        if state == 65:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 65
                return i
            if char == 'p':
                state = 66
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'o':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'q' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 66:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 66
                return i
            if char == 'r':
                state = 67
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'q':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 's' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 67:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 67
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'f' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'd':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'e':
                state = 68
            else:
                break
        if state == 68:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 68
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'e' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'c':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'd':
                state = 69
            else:
                break
        if state == 69:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 69
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'j' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'h':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'i':
                state = 70
            else:
                break
        if state == 70:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 70
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'd' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == 'a':
                state = 11
                continue
            elif char == 'b':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'c':
                state = 71
            else:
                break
        if state == 71:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 71
                return i
            if char == 'a':
                state = 72
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'b' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 72:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 72
                return i
            if char == 't':
                state = 73
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 's':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'u' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 73:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 73
                return i
            if char == 'e':
                state = 74
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'f' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'd':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 74:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 74
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 75:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 75
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'j' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'h':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'i':
                state = 77
            else:
                break
        if state == 76:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 76
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 77:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 77
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 's':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'u' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 't':
                state = 78
            else:
                break
        if state == 78:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 78
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'j' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'h':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'i':
                state = 79
            else:
                break
        if state == 79:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 79
                return i
            if char == 'a':
                state = 80
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'b' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 80:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 80
                return i
            if char == 'l':
                state = 81
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'm' <= char <= 'z':
                state = 11
                continue
            elif 'a' <= char <= 'k':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 81:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 81
                return i
            if char == 'i':
                state = 82
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'j' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'h':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 82:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 82
                return i
            if char == 'z':
                state = 83
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'y':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 83:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 83
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'b' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'a':
                state = 84
            else:
                break
        if state == 84:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 84
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 's':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'u' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 't':
                state = 85
            else:
                break
        if state == 85:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 85
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'j' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'h':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'i':
                state = 86
            else:
                break
        if state == 86:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 86
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'n':
                state = 11
                continue
            elif 'p' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'o':
                state = 87
            else:
                break
        if state == 87:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 87
                return i
            if char == 'n':
                state = 88
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'm':
                state = 11
                continue
            elif 'o' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 88:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 88
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 89:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 89
                return ~i
            if char == '=':
                state = 98
            else:
                break
        if state == 91:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 91
                return ~i
            if char == '.':
                state = 97
            else:
                break
        if state == 92:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 92
                return ~i
            if char == '=':
                state = 96
            else:
                break
        if state == 94:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 94
                return ~i
            if char == '=':
                state = 95
            else:
                break
        if state == 99:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 99
                return ~i
            if char == '>':
                state = 101
            else:
                break
        if state == 102:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 102
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'n' <= char <= 'z':
                state = 11
                continue
            elif 'a' <= char <= 'l':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'm':
                state = 103
            else:
                break
        if state == 103:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 103
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 109:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 109
                return ~i
            if char == '*':
                state = 112
            elif '+' <= char <= '\xff':
                state = 109
                continue
            elif '\x00' <= char <= ')':
                state = 109
                continue
            else:
                break
        if state == 112:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 112
                return ~i
            if char == '/':
                state = 1
            elif '0' <= char <= '\xff':
                state = 109
                continue
            elif '\x00' <= char <= '.':
                state = 109
                continue
            else:
                break
        if state == 113:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 113
                return i
            if char == 'r':
                state = 114
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'q':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 's' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 114:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 114
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 115:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 115
                return i
            if char == 's':
                state = 122
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'r':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 't' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 116:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 116
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'm':
                state = 11
                continue
            elif 'o' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'n':
                state = 117
            else:
                break
        if state == 117:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 117
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'b' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'a':
                state = 118
            else:
                break
        if state == 118:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 118
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'n' <= char <= 'z':
                state = 11
                continue
            elif 'a' <= char <= 'l':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'm':
                state = 119
            else:
                break
        if state == 119:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 119
                return i
            if char == 'i':
                state = 120
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'j' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'h':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 120:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 120
                return i
            if char == 'c':
                state = 121
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'd' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == 'a':
                state = 11
                continue
            elif char == 'b':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 121:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 121
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 122:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 122
                return i
            if char == 'c':
                state = 123
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'd' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == 'a':
                state = 11
                continue
            elif char == 'b':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 123:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 123
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'n':
                state = 11
                continue
            elif 'p' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'o':
                state = 124
            else:
                break
        if state == 124:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 124
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'm':
                state = 11
                continue
            elif 'o' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'n':
                state = 125
            else:
                break
        if state == 125:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 125
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 's':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'u' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 't':
                state = 126
            else:
                break
        if state == 126:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 126
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'j' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'h':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'i':
                state = 127
            else:
                break
        if state == 127:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 127
                return i
            if char == 'g':
                state = 128
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'h' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'a' <= char <= 'f':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 128:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 128
                return i
            if char == 'u':
                state = 129
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 't':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'v' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 129:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 129
                return i
            if char == 'o':
                state = 130
            elif 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'n':
                state = 11
                continue
            elif 'p' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 130:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 130
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 't':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 'v' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 'u':
                state = 131
            else:
                break
        if state == 131:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 131
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'r':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif 't' <= char <= 'z':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            elif char == 's':
                state = 132
            else:
                break
        if state == 132:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 132
                return i
            if 'A' <= char <= 'Z':
                state = 11
                continue
            elif 'a' <= char <= 'z':
                state = 11
                continue
            elif '0' <= char <= '9':
                state = 11
                continue
            elif char == '_':
                state = 11
                continue
            else:
                break
        if state == 134:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 134
                return i
            if char == '=':
                state = 136
            else:
                break
        if state == 137:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 137
                return ~i
            if char == '<':
                state = 141
            else:
                break
        if state == 139:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 139
                return i
            if char == '=':
                state = 140
            else:
                break
        if state == 143:
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 143
                return ~i
            if '0' <= char <= '9':
                state = 144
            else:
                break
        if state == 144:
            runner.last_matched_index = i - 1
            runner.last_matched_state = state
            try:
                char = input[i]
                i += 1
            except IndexError:
                runner.state = 144
                return i
            if '0' <= char <= '9':
                state = 144
                continue
            else:
                break
        runner.last_matched_state = state
        runner.last_matched_index = i - 1
        runner.state = state
        if i == len(input):
            return i
        else:
            return ~i
        break
    runner.state = state
    return ~i
lexer = DummyLexer(recognize, DFA(145,
 {(0, '\t'): 1,
  (0, '\n'): 1,
  (0, ' '): 1,
  (0, '!'): 14,
  (0, '#'): 14,
  (0, '%'): 29,
  (0, '&'): 14,
  (0, "'"): 15,
  (0, '('): 2,
  (0, ')'): 30,
  (0, '*'): 22,
  (0, '+'): 16,
  (0, ','): 3,
  (0, '-'): 31,
  (0, '.'): 23,
  (0, '/'): 17,
  (0, '0'): 4,
  (0, '1'): 5,
  (0, '2'): 5,
  (0, '3'): 5,
  (0, '4'): 5,
  (0, '5'): 5,
  (0, '6'): 5,
  (0, '7'): 5,
  (0, '8'): 5,
  (0, '9'): 5,
  (0, ':'): 24,
  (0, ';'): 18,
  (0, '<'): 6,
  (0, '='): 32,
  (0, '>'): 25,
  (0, '?'): 19,
  (0, '@'): 7,
  (0, 'A'): 8,
  (0, 'B'): 8,
  (0, 'C'): 8,
  (0, 'D'): 8,
  (0, 'E'): 8,
  (0, 'F'): 8,
  (0, 'G'): 8,
  (0, 'H'): 8,
  (0, 'I'): 8,
  (0, 'J'): 8,
  (0, 'K'): 8,
  (0, 'L'): 8,
  (0, 'M'): 8,
  (0, 'N'): 8,
  (0, 'O'): 8,
  (0, 'P'): 8,
  (0, 'Q'): 8,
  (0, 'R'): 8,
  (0, 'S'): 8,
  (0, 'T'): 8,
  (0, 'U'): 8,
  (0, 'V'): 8,
  (0, 'W'): 8,
  (0, 'X'): 8,
  (0, 'Y'): 8,
  (0, 'Z'): 8,
  (0, '['): 20,
  (0, '\\'): 9,
  (0, ']'): 33,
  (0, '^'): 26,
  (0, '_'): 8,
  (0, 'a'): 11,
  (0, 'b'): 11,
  (0, 'c'): 11,
  (0, 'd'): 10,
  (0, 'e'): 11,
  (0, 'f'): 11,
  (0, 'g'): 11,
  (0, 'h'): 11,
  (0, 'i'): 34,
  (0, 'j'): 11,
  (0, 'k'): 11,
  (0, 'l'): 11,
  (0, 'm'): 35,
  (0, 'n'): 11,
  (0, 'o'): 11,
  (0, 'p'): 11,
  (0, 'q'): 11,
  (0, 'r'): 27,
  (0, 's'): 11,
  (0, 't'): 11,
  (0, 'u'): 11,
  (0, 'v'): 11,
  (0, 'w'): 11,
  (0, 'x'): 12,
  (0, 'y'): 11,
  (0, 'z'): 11,
  (0, '{'): 21,
  (0, '|'): 13,
  (0, '}'): 36,
  (0, '~'): 28,
  (4, '.'): 143,
  (5, '.'): 143,
  (5, '0'): 5,
  (5, '1'): 5,
  (5, '2'): 5,
  (5, '3'): 5,
  (5, '4'): 5,
  (5, '5'): 5,
  (5, '6'): 5,
  (5, '7'): 5,
  (5, '8'): 5,
  (5, '9'): 5,
  (6, '<'): 142,
  (7, '<'): 138,
  (7, '='): 137,
  (7, '>'): 139,
  (8, '0'): 8,
  (8, '1'): 8,
  (8, '2'): 8,
  (8, '3'): 8,
  (8, '4'): 8,
  (8, '5'): 8,
  (8, '6'): 8,
  (8, '7'): 8,
  (8, '8'): 8,
  (8, '9'): 8,
  (8, 'A'): 8,
  (8, 'B'): 8,
  (8, 'C'): 8,
  (8, 'D'): 8,
  (8, 'E'): 8,
  (8, 'F'): 8,
  (8, 'G'): 8,
  (8, 'H'): 8,
  (8, 'I'): 8,
  (8, 'J'): 8,
  (8, 'K'): 8,
  (8, 'L'): 8,
  (8, 'M'): 8,
  (8, 'N'): 8,
  (8, 'O'): 8,
  (8, 'P'): 8,
  (8, 'Q'): 8,
  (8, 'R'): 8,
  (8, 'S'): 8,
  (8, 'T'): 8,
  (8, 'U'): 8,
  (8, 'V'): 8,
  (8, 'W'): 8,
  (8, 'X'): 8,
  (8, 'Y'): 8,
  (8, 'Z'): 8,
  (8, '_'): 8,
  (8, 'a'): 8,
  (8, 'b'): 8,
  (8, 'c'): 8,
  (8, 'd'): 8,
  (8, 'e'): 8,
  (8, 'f'): 8,
  (8, 'g'): 8,
  (8, 'h'): 8,
  (8, 'i'): 8,
  (8, 'j'): 8,
  (8, 'k'): 8,
  (8, 'l'): 8,
  (8, 'm'): 8,
  (8, 'n'): 8,
  (8, 'o'): 8,
  (8, 'p'): 8,
  (8, 'q'): 8,
  (8, 'r'): 8,
  (8, 's'): 8,
  (8, 't'): 8,
  (8, 'u'): 8,
  (8, 'v'): 8,
  (8, 'w'): 8,
  (8, 'x'): 8,
  (8, 'y'): 8,
  (8, 'z'): 8,
  (9, '+'): 133,
  (9, '/'): 135,
  (9, '='): 134,
  (10, '0'): 11,
  (10, '1'): 11,
  (10, '2'): 11,
  (10, '3'): 11,
  (10, '4'): 11,
  (10, '5'): 11,
  (10, '6'): 11,
  (10, '7'): 11,
  (10, '8'): 11,
  (10, '9'): 11,
  (10, 'A'): 11,
  (10, 'B'): 11,
  (10, 'C'): 11,
  (10, 'D'): 11,
  (10, 'E'): 11,
  (10, 'F'): 11,
  (10, 'G'): 11,
  (10, 'H'): 11,
  (10, 'I'): 11,
  (10, 'J'): 11,
  (10, 'K'): 11,
  (10, 'L'): 11,
  (10, 'M'): 11,
  (10, 'N'): 11,
  (10, 'O'): 11,
  (10, 'P'): 11,
  (10, 'Q'): 11,
  (10, 'R'): 11,
  (10, 'S'): 11,
  (10, 'T'): 11,
  (10, 'U'): 11,
  (10, 'V'): 11,
  (10, 'W'): 11,
  (10, 'X'): 11,
  (10, 'Y'): 11,
  (10, 'Z'): 11,
  (10, '_'): 11,
  (10, 'a'): 11,
  (10, 'b'): 11,
  (10, 'c'): 11,
  (10, 'd'): 11,
  (10, 'e'): 11,
  (10, 'f'): 11,
  (10, 'g'): 11,
  (10, 'h'): 11,
  (10, 'i'): 115,
  (10, 'j'): 11,
  (10, 'k'): 11,
  (10, 'l'): 11,
  (10, 'm'): 11,
  (10, 'n'): 11,
  (10, 'o'): 11,
  (10, 'p'): 11,
  (10, 'q'): 11,
  (10, 'r'): 11,
  (10, 's'): 11,
  (10, 't'): 11,
  (10, 'u'): 11,
  (10, 'v'): 11,
  (10, 'w'): 11,
  (10, 'x'): 11,
  (10, 'y'): 116,
  (10, 'z'): 11,
  (11, '0'): 11,
  (11, '1'): 11,
  (11, '2'): 11,
  (11, '3'): 11,
  (11, '4'): 11,
  (11, '5'): 11,
  (11, '6'): 11,
  (11, '7'): 11,
  (11, '8'): 11,
  (11, '9'): 11,
  (11, 'A'): 11,
  (11, 'B'): 11,
  (11, 'C'): 11,
  (11, 'D'): 11,
  (11, 'E'): 11,
  (11, 'F'): 11,
  (11, 'G'): 11,
  (11, 'H'): 11,
  (11, 'I'): 11,
  (11, 'J'): 11,
  (11, 'K'): 11,
  (11, 'L'): 11,
  (11, 'M'): 11,
  (11, 'N'): 11,
  (11, 'O'): 11,
  (11, 'P'): 11,
  (11, 'Q'): 11,
  (11, 'R'): 11,
  (11, 'S'): 11,
  (11, 'T'): 11,
  (11, 'U'): 11,
  (11, 'V'): 11,
  (11, 'W'): 11,
  (11, 'X'): 11,
  (11, 'Y'): 11,
  (11, 'Z'): 11,
  (11, '_'): 11,
  (11, 'a'): 11,
  (11, 'b'): 11,
  (11, 'c'): 11,
  (11, 'd'): 11,
  (11, 'e'): 11,
  (11, 'f'): 11,
  (11, 'g'): 11,
  (11, 'h'): 11,
  (11, 'i'): 11,
  (11, 'j'): 11,
  (11, 'k'): 11,
  (11, 'l'): 11,
  (11, 'm'): 11,
  (11, 'n'): 11,
  (11, 'o'): 11,
  (11, 'p'): 11,
  (11, 'q'): 11,
  (11, 'r'): 11,
  (11, 's'): 11,
  (11, 't'): 11,
  (11, 'u'): 11,
  (11, 'v'): 11,
  (11, 'w'): 11,
  (11, 'x'): 11,
  (11, 'y'): 11,
  (11, 'z'): 11,
  (12, '0'): 11,
  (12, '1'): 11,
  (12, '2'): 11,
  (12, '3'): 11,
  (12, '4'): 11,
  (12, '5'): 11,
  (12, '6'): 11,
  (12, '7'): 11,
  (12, '8'): 11,
  (12, '9'): 11,
  (12, 'A'): 11,
  (12, 'B'): 11,
  (12, 'C'): 11,
  (12, 'D'): 11,
  (12, 'E'): 11,
  (12, 'F'): 11,
  (12, 'G'): 11,
  (12, 'H'): 11,
  (12, 'I'): 11,
  (12, 'J'): 11,
  (12, 'K'): 11,
  (12, 'L'): 11,
  (12, 'M'): 11,
  (12, 'N'): 11,
  (12, 'O'): 11,
  (12, 'P'): 11,
  (12, 'Q'): 11,
  (12, 'R'): 11,
  (12, 'S'): 11,
  (12, 'T'): 11,
  (12, 'U'): 11,
  (12, 'V'): 11,
  (12, 'W'): 11,
  (12, 'X'): 11,
  (12, 'Y'): 11,
  (12, 'Z'): 11,
  (12, '_'): 11,
  (12, 'a'): 11,
  (12, 'b'): 11,
  (12, 'c'): 11,
  (12, 'd'): 11,
  (12, 'e'): 11,
  (12, 'f'): 11,
  (12, 'g'): 11,
  (12, 'h'): 11,
  (12, 'i'): 11,
  (12, 'j'): 11,
  (12, 'k'): 11,
  (12, 'l'): 11,
  (12, 'm'): 11,
  (12, 'n'): 11,
  (12, 'o'): 113,
  (12, 'p'): 11,
  (12, 'q'): 11,
  (12, 'r'): 11,
  (12, 's'): 11,
  (12, 't'): 11,
  (12, 'u'): 11,
  (12, 'v'): 11,
  (12, 'w'): 11,
  (12, 'x'): 11,
  (12, 'y'): 11,
  (12, 'z'): 11,
  (15, '\x00'): 15,
  (15, '\x01'): 15,
  (15, '\x02'): 15,
  (15, '\x03'): 15,
  (15, '\x04'): 15,
  (15, '\x05'): 15,
  (15, '\x06'): 15,
  (15, '\x07'): 15,
  (15, '\x08'): 15,
  (15, '\t'): 15,
  (15, '\n'): 15,
  (15, '\x0b'): 15,
  (15, '\x0c'): 15,
  (15, '\r'): 15,
  (15, '\x0e'): 15,
  (15, '\x0f'): 15,
  (15, '\x10'): 15,
  (15, '\x11'): 15,
  (15, '\x12'): 15,
  (15, '\x13'): 15,
  (15, '\x14'): 15,
  (15, '\x15'): 15,
  (15, '\x16'): 15,
  (15, '\x17'): 15,
  (15, '\x18'): 15,
  (15, '\x19'): 15,
  (15, '\x1a'): 15,
  (15, '\x1b'): 15,
  (15, '\x1c'): 15,
  (15, '\x1d'): 15,
  (15, '\x1e'): 15,
  (15, '\x1f'): 15,
  (15, ' '): 15,
  (15, '!'): 15,
  (15, '"'): 15,
  (15, '#'): 15,
  (15, '$'): 15,
  (15, '%'): 15,
  (15, '&'): 15,
  (15, "'"): 14,
  (15, '('): 15,
  (15, ')'): 15,
  (15, '*'): 15,
  (15, '+'): 15,
  (15, ','): 15,
  (15, '-'): 15,
  (15, '.'): 15,
  (15, '/'): 15,
  (15, '0'): 15,
  (15, '1'): 15,
  (15, '2'): 15,
  (15, '3'): 15,
  (15, '4'): 15,
  (15, '5'): 15,
  (15, '6'): 15,
  (15, '7'): 15,
  (15, '8'): 15,
  (15, '9'): 15,
  (15, ':'): 15,
  (15, ';'): 15,
  (15, '<'): 15,
  (15, '='): 15,
  (15, '>'): 15,
  (15, '?'): 15,
  (15, '@'): 15,
  (15, 'A'): 15,
  (15, 'B'): 15,
  (15, 'C'): 15,
  (15, 'D'): 15,
  (15, 'E'): 15,
  (15, 'F'): 15,
  (15, 'G'): 15,
  (15, 'H'): 15,
  (15, 'I'): 15,
  (15, 'J'): 15,
  (15, 'K'): 15,
  (15, 'L'): 15,
  (15, 'M'): 15,
  (15, 'N'): 15,
  (15, 'O'): 15,
  (15, 'P'): 15,
  (15, 'Q'): 15,
  (15, 'R'): 15,
  (15, 'S'): 15,
  (15, 'T'): 15,
  (15, 'U'): 15,
  (15, 'V'): 15,
  (15, 'W'): 15,
  (15, 'X'): 15,
  (15, 'Y'): 15,
  (15, 'Z'): 15,
  (15, '['): 15,
  (15, '\\'): 15,
  (15, ']'): 15,
  (15, '^'): 15,
  (15, '_'): 15,
  (15, '`'): 15,
  (15, 'a'): 15,
  (15, 'b'): 15,
  (15, 'c'): 15,
  (15, 'd'): 15,
  (15, 'e'): 15,
  (15, 'f'): 15,
  (15, 'g'): 15,
  (15, 'h'): 15,
  (15, 'i'): 15,
  (15, 'j'): 15,
  (15, 'k'): 15,
  (15, 'l'): 15,
  (15, 'm'): 15,
  (15, 'n'): 15,
  (15, 'o'): 15,
  (15, 'p'): 15,
  (15, 'q'): 15,
  (15, 'r'): 15,
  (15, 's'): 15,
  (15, 't'): 15,
  (15, 'u'): 15,
  (15, 'v'): 15,
  (15, 'w'): 15,
  (15, 'x'): 15,
  (15, 'y'): 15,
  (15, 'z'): 15,
  (15, '{'): 15,
  (15, '|'): 15,
  (15, '}'): 15,
  (15, '~'): 15,
  (15, '\x7f'): 15,
  (15, '\x80'): 15,
  (15, '\x81'): 15,
  (15, '\x82'): 15,
  (15, '\x83'): 15,
  (15, '\x84'): 15,
  (15, '\x85'): 15,
  (15, '\x86'): 15,
  (15, '\x87'): 15,
  (15, '\x88'): 15,
  (15, '\x89'): 15,
  (15, '\x8a'): 15,
  (15, '\x8b'): 15,
  (15, '\x8c'): 15,
  (15, '\x8d'): 15,
  (15, '\x8e'): 15,
  (15, '\x8f'): 15,
  (15, '\x90'): 15,
  (15, '\x91'): 15,
  (15, '\x92'): 15,
  (15, '\x93'): 15,
  (15, '\x94'): 15,
  (15, '\x95'): 15,
  (15, '\x96'): 15,
  (15, '\x97'): 15,
  (15, '\x98'): 15,
  (15, '\x99'): 15,
  (15, '\x9a'): 15,
  (15, '\x9b'): 15,
  (15, '\x9c'): 15,
  (15, '\x9d'): 15,
  (15, '\x9e'): 15,
  (15, '\x9f'): 15,
  (15, '\xa0'): 15,
  (15, '\xa1'): 15,
  (15, '\xa2'): 15,
  (15, '\xa3'): 15,
  (15, '\xa4'): 15,
  (15, '\xa5'): 15,
  (15, '\xa6'): 15,
  (15, '\xa7'): 15,
  (15, '\xa8'): 15,
  (15, '\xa9'): 15,
  (15, '\xaa'): 15,
  (15, '\xab'): 15,
  (15, '\xac'): 15,
  (15, '\xad'): 15,
  (15, '\xae'): 15,
  (15, '\xaf'): 15,
  (15, '\xb0'): 15,
  (15, '\xb1'): 15,
  (15, '\xb2'): 15,
  (15, '\xb3'): 15,
  (15, '\xb4'): 15,
  (15, '\xb5'): 15,
  (15, '\xb6'): 15,
  (15, '\xb7'): 15,
  (15, '\xb8'): 15,
  (15, '\xb9'): 15,
  (15, '\xba'): 15,
  (15, '\xbb'): 15,
  (15, '\xbc'): 15,
  (15, '\xbd'): 15,
  (15, '\xbe'): 15,
  (15, '\xbf'): 15,
  (15, '\xc0'): 15,
  (15, '\xc1'): 15,
  (15, '\xc2'): 15,
  (15, '\xc3'): 15,
  (15, '\xc4'): 15,
  (15, '\xc5'): 15,
  (15, '\xc6'): 15,
  (15, '\xc7'): 15,
  (15, '\xc8'): 15,
  (15, '\xc9'): 15,
  (15, '\xca'): 15,
  (15, '\xcb'): 15,
  (15, '\xcc'): 15,
  (15, '\xcd'): 15,
  (15, '\xce'): 15,
  (15, '\xcf'): 15,
  (15, '\xd0'): 15,
  (15, '\xd1'): 15,
  (15, '\xd2'): 15,
  (15, '\xd3'): 15,
  (15, '\xd4'): 15,
  (15, '\xd5'): 15,
  (15, '\xd6'): 15,
  (15, '\xd7'): 15,
  (15, '\xd8'): 15,
  (15, '\xd9'): 15,
  (15, '\xda'): 15,
  (15, '\xdb'): 15,
  (15, '\xdc'): 15,
  (15, '\xdd'): 15,
  (15, '\xde'): 15,
  (15, '\xdf'): 15,
  (15, '\xe0'): 15,
  (15, '\xe1'): 15,
  (15, '\xe2'): 15,
  (15, '\xe3'): 15,
  (15, '\xe4'): 15,
  (15, '\xe5'): 15,
  (15, '\xe6'): 15,
  (15, '\xe7'): 15,
  (15, '\xe8'): 15,
  (15, '\xe9'): 15,
  (15, '\xea'): 15,
  (15, '\xeb'): 15,
  (15, '\xec'): 15,
  (15, '\xed'): 15,
  (15, '\xee'): 15,
  (15, '\xef'): 15,
  (15, '\xf0'): 15,
  (15, '\xf1'): 15,
  (15, '\xf2'): 15,
  (15, '\xf3'): 15,
  (15, '\xf4'): 15,
  (15, '\xf5'): 15,
  (15, '\xf6'): 15,
  (15, '\xf7'): 15,
  (15, '\xf8'): 15,
  (15, '\xf9'): 15,
  (15, '\xfa'): 15,
  (15, '\xfb'): 15,
  (15, '\xfc'): 15,
  (15, '\xfd'): 15,
  (15, '\xfe'): 15,
  (15, '\xff'): 15,
  (17, '*'): 109,
  (17, '/'): 111,
  (17, '\\'): 110,
  (19, '-'): 108,
  (20, ']'): 14,
  (22, '*'): 107,
  (24, '-'): 106,
  (25, '='): 104,
  (25, '>'): 105,
  (27, '0'): 11,
  (27, '1'): 11,
  (27, '2'): 11,
  (27, '3'): 11,
  (27, '4'): 11,
  (27, '5'): 11,
  (27, '6'): 11,
  (27, '7'): 11,
  (27, '8'): 11,
  (27, '9'): 11,
  (27, 'A'): 11,
  (27, 'B'): 11,
  (27, 'C'): 11,
  (27, 'D'): 11,
  (27, 'E'): 11,
  (27, 'F'): 11,
  (27, 'G'): 11,
  (27, 'H'): 11,
  (27, 'I'): 11,
  (27, 'J'): 11,
  (27, 'K'): 11,
  (27, 'L'): 11,
  (27, 'M'): 11,
  (27, 'N'): 11,
  (27, 'O'): 11,
  (27, 'P'): 11,
  (27, 'Q'): 11,
  (27, 'R'): 11,
  (27, 'S'): 11,
  (27, 'T'): 11,
  (27, 'U'): 11,
  (27, 'V'): 11,
  (27, 'W'): 11,
  (27, 'X'): 11,
  (27, 'Y'): 11,
  (27, 'Z'): 11,
  (27, '_'): 11,
  (27, 'a'): 11,
  (27, 'b'): 11,
  (27, 'c'): 11,
  (27, 'd'): 11,
  (27, 'e'): 102,
  (27, 'f'): 11,
  (27, 'g'): 11,
  (27, 'h'): 11,
  (27, 'i'): 11,
  (27, 'j'): 11,
  (27, 'k'): 11,
  (27, 'l'): 11,
  (27, 'm'): 11,
  (27, 'n'): 11,
  (27, 'o'): 11,
  (27, 'p'): 11,
  (27, 'q'): 11,
  (27, 'r'): 11,
  (27, 's'): 11,
  (27, 't'): 11,
  (27, 'u'): 11,
  (27, 'v'): 11,
  (27, 'w'): 11,
  (27, 'x'): 11,
  (27, 'y'): 11,
  (27, 'z'): 11,
  (29, '\x00'): 29,
  (29, '\x01'): 29,
  (29, '\x02'): 29,
  (29, '\x03'): 29,
  (29, '\x04'): 29,
  (29, '\x05'): 29,
  (29, '\x06'): 29,
  (29, '\x07'): 29,
  (29, '\x08'): 29,
  (29, '\t'): 29,
  (29, '\x0b'): 29,
  (29, '\x0c'): 29,
  (29, '\r'): 29,
  (29, '\x0e'): 29,
  (29, '\x0f'): 29,
  (29, '\x10'): 29,
  (29, '\x11'): 29,
  (29, '\x12'): 29,
  (29, '\x13'): 29,
  (29, '\x14'): 29,
  (29, '\x15'): 29,
  (29, '\x16'): 29,
  (29, '\x17'): 29,
  (29, '\x18'): 29,
  (29, '\x19'): 29,
  (29, '\x1a'): 29,
  (29, '\x1b'): 29,
  (29, '\x1c'): 29,
  (29, '\x1d'): 29,
  (29, '\x1e'): 29,
  (29, '\x1f'): 29,
  (29, ' '): 29,
  (29, '!'): 29,
  (29, '"'): 29,
  (29, '#'): 29,
  (29, '$'): 29,
  (29, '%'): 29,
  (29, '&'): 29,
  (29, "'"): 29,
  (29, '('): 29,
  (29, ')'): 29,
  (29, '*'): 29,
  (29, '+'): 29,
  (29, ','): 29,
  (29, '-'): 29,
  (29, '.'): 29,
  (29, '/'): 29,
  (29, '0'): 29,
  (29, '1'): 29,
  (29, '2'): 29,
  (29, '3'): 29,
  (29, '4'): 29,
  (29, '5'): 29,
  (29, '6'): 29,
  (29, '7'): 29,
  (29, '8'): 29,
  (29, '9'): 29,
  (29, ':'): 29,
  (29, ';'): 29,
  (29, '<'): 29,
  (29, '='): 29,
  (29, '>'): 29,
  (29, '?'): 29,
  (29, '@'): 29,
  (29, 'A'): 29,
  (29, 'B'): 29,
  (29, 'C'): 29,
  (29, 'D'): 29,
  (29, 'E'): 29,
  (29, 'F'): 29,
  (29, 'G'): 29,
  (29, 'H'): 29,
  (29, 'I'): 29,
  (29, 'J'): 29,
  (29, 'K'): 29,
  (29, 'L'): 29,
  (29, 'M'): 29,
  (29, 'N'): 29,
  (29, 'O'): 29,
  (29, 'P'): 29,
  (29, 'Q'): 29,
  (29, 'R'): 29,
  (29, 'S'): 29,
  (29, 'T'): 29,
  (29, 'U'): 29,
  (29, 'V'): 29,
  (29, 'W'): 29,
  (29, 'X'): 29,
  (29, 'Y'): 29,
  (29, 'Z'): 29,
  (29, '['): 29,
  (29, '\\'): 29,
  (29, ']'): 29,
  (29, '^'): 29,
  (29, '_'): 29,
  (29, '`'): 29,
  (29, 'a'): 29,
  (29, 'b'): 29,
  (29, 'c'): 29,
  (29, 'd'): 29,
  (29, 'e'): 29,
  (29, 'f'): 29,
  (29, 'g'): 29,
  (29, 'h'): 29,
  (29, 'i'): 29,
  (29, 'j'): 29,
  (29, 'k'): 29,
  (29, 'l'): 29,
  (29, 'm'): 29,
  (29, 'n'): 29,
  (29, 'o'): 29,
  (29, 'p'): 29,
  (29, 'q'): 29,
  (29, 'r'): 29,
  (29, 's'): 29,
  (29, 't'): 29,
  (29, 'u'): 29,
  (29, 'v'): 29,
  (29, 'w'): 29,
  (29, 'x'): 29,
  (29, 'y'): 29,
  (29, 'z'): 29,
  (29, '{'): 29,
  (29, '|'): 29,
  (29, '}'): 29,
  (29, '~'): 29,
  (29, '\x7f'): 29,
  (29, '\x80'): 29,
  (29, '\x81'): 29,
  (29, '\x82'): 29,
  (29, '\x83'): 29,
  (29, '\x84'): 29,
  (29, '\x85'): 29,
  (29, '\x86'): 29,
  (29, '\x87'): 29,
  (29, '\x88'): 29,
  (29, '\x89'): 29,
  (29, '\x8a'): 29,
  (29, '\x8b'): 29,
  (29, '\x8c'): 29,
  (29, '\x8d'): 29,
  (29, '\x8e'): 29,
  (29, '\x8f'): 29,
  (29, '\x90'): 29,
  (29, '\x91'): 29,
  (29, '\x92'): 29,
  (29, '\x93'): 29,
  (29, '\x94'): 29,
  (29, '\x95'): 29,
  (29, '\x96'): 29,
  (29, '\x97'): 29,
  (29, '\x98'): 29,
  (29, '\x99'): 29,
  (29, '\x9a'): 29,
  (29, '\x9b'): 29,
  (29, '\x9c'): 29,
  (29, '\x9d'): 29,
  (29, '\x9e'): 29,
  (29, '\x9f'): 29,
  (29, '\xa0'): 29,
  (29, '\xa1'): 29,
  (29, '\xa2'): 29,
  (29, '\xa3'): 29,
  (29, '\xa4'): 29,
  (29, '\xa5'): 29,
  (29, '\xa6'): 29,
  (29, '\xa7'): 29,
  (29, '\xa8'): 29,
  (29, '\xa9'): 29,
  (29, '\xaa'): 29,
  (29, '\xab'): 29,
  (29, '\xac'): 29,
  (29, '\xad'): 29,
  (29, '\xae'): 29,
  (29, '\xaf'): 29,
  (29, '\xb0'): 29,
  (29, '\xb1'): 29,
  (29, '\xb2'): 29,
  (29, '\xb3'): 29,
  (29, '\xb4'): 29,
  (29, '\xb5'): 29,
  (29, '\xb6'): 29,
  (29, '\xb7'): 29,
  (29, '\xb8'): 29,
  (29, '\xb9'): 29,
  (29, '\xba'): 29,
  (29, '\xbb'): 29,
  (29, '\xbc'): 29,
  (29, '\xbd'): 29,
  (29, '\xbe'): 29,
  (29, '\xbf'): 29,
  (29, '\xc0'): 29,
  (29, '\xc1'): 29,
  (29, '\xc2'): 29,
  (29, '\xc3'): 29,
  (29, '\xc4'): 29,
  (29, '\xc5'): 29,
  (29, '\xc6'): 29,
  (29, '\xc7'): 29,
  (29, '\xc8'): 29,
  (29, '\xc9'): 29,
  (29, '\xca'): 29,
  (29, '\xcb'): 29,
  (29, '\xcc'): 29,
  (29, '\xcd'): 29,
  (29, '\xce'): 29,
  (29, '\xcf'): 29,
  (29, '\xd0'): 29,
  (29, '\xd1'): 29,
  (29, '\xd2'): 29,
  (29, '\xd3'): 29,
  (29, '\xd4'): 29,
  (29, '\xd5'): 29,
  (29, '\xd6'): 29,
  (29, '\xd7'): 29,
  (29, '\xd8'): 29,
  (29, '\xd9'): 29,
  (29, '\xda'): 29,
  (29, '\xdb'): 29,
  (29, '\xdc'): 29,
  (29, '\xdd'): 29,
  (29, '\xde'): 29,
  (29, '\xdf'): 29,
  (29, '\xe0'): 29,
  (29, '\xe1'): 29,
  (29, '\xe2'): 29,
  (29, '\xe3'): 29,
  (29, '\xe4'): 29,
  (29, '\xe5'): 29,
  (29, '\xe6'): 29,
  (29, '\xe7'): 29,
  (29, '\xe8'): 29,
  (29, '\xe9'): 29,
  (29, '\xea'): 29,
  (29, '\xeb'): 29,
  (29, '\xec'): 29,
  (29, '\xed'): 29,
  (29, '\xee'): 29,
  (29, '\xef'): 29,
  (29, '\xf0'): 29,
  (29, '\xf1'): 29,
  (29, '\xf2'): 29,
  (29, '\xf3'): 29,
  (29, '\xf4'): 29,
  (29, '\xf5'): 29,
  (29, '\xf6'): 29,
  (29, '\xf7'): 29,
  (29, '\xf8'): 29,
  (29, '\xf9'): 29,
  (29, '\xfa'): 29,
  (29, '\xfb'): 29,
  (29, '\xfc'): 29,
  (29, '\xfd'): 29,
  (29, '\xfe'): 29,
  (29, '\xff'): 29,
  (31, '-'): 99,
  (31, '>'): 100,
  (32, '.'): 91,
  (32, ':'): 92,
  (32, '<'): 90,
  (32, '='): 93,
  (32, '@'): 89,
  (32, '\\'): 94,
  (34, '0'): 11,
  (34, '1'): 11,
  (34, '2'): 11,
  (34, '3'): 11,
  (34, '4'): 11,
  (34, '5'): 11,
  (34, '6'): 11,
  (34, '7'): 11,
  (34, '8'): 11,
  (34, '9'): 11,
  (34, 'A'): 11,
  (34, 'B'): 11,
  (34, 'C'): 11,
  (34, 'D'): 11,
  (34, 'E'): 11,
  (34, 'F'): 11,
  (34, 'G'): 11,
  (34, 'H'): 11,
  (34, 'I'): 11,
  (34, 'J'): 11,
  (34, 'K'): 11,
  (34, 'L'): 11,
  (34, 'M'): 11,
  (34, 'N'): 11,
  (34, 'O'): 11,
  (34, 'P'): 11,
  (34, 'Q'): 11,
  (34, 'R'): 11,
  (34, 'S'): 11,
  (34, 'T'): 11,
  (34, 'U'): 11,
  (34, 'V'): 11,
  (34, 'W'): 11,
  (34, 'X'): 11,
  (34, 'Y'): 11,
  (34, 'Z'): 11,
  (34, '_'): 11,
  (34, 'a'): 11,
  (34, 'b'): 11,
  (34, 'c'): 11,
  (34, 'd'): 11,
  (34, 'e'): 11,
  (34, 'f'): 11,
  (34, 'g'): 11,
  (34, 'h'): 11,
  (34, 'i'): 11,
  (34, 'j'): 11,
  (34, 'k'): 11,
  (34, 'l'): 11,
  (34, 'm'): 11,
  (34, 'n'): 75,
  (34, 'o'): 11,
  (34, 'p'): 11,
  (34, 'q'): 11,
  (34, 'r'): 11,
  (34, 's'): 76,
  (34, 't'): 11,
  (34, 'u'): 11,
  (34, 'v'): 11,
  (34, 'w'): 11,
  (34, 'x'): 11,
  (34, 'y'): 11,
  (34, 'z'): 11,
  (35, '0'): 11,
  (35, '1'): 11,
  (35, '2'): 11,
  (35, '3'): 11,
  (35, '4'): 11,
  (35, '5'): 11,
  (35, '6'): 11,
  (35, '7'): 11,
  (35, '8'): 11,
  (35, '9'): 11,
  (35, 'A'): 11,
  (35, 'B'): 11,
  (35, 'C'): 11,
  (35, 'D'): 11,
  (35, 'E'): 11,
  (35, 'F'): 11,
  (35, 'G'): 11,
  (35, 'H'): 11,
  (35, 'I'): 11,
  (35, 'J'): 11,
  (35, 'K'): 11,
  (35, 'L'): 11,
  (35, 'M'): 11,
  (35, 'N'): 11,
  (35, 'O'): 11,
  (35, 'P'): 11,
  (35, 'Q'): 11,
  (35, 'R'): 11,
  (35, 'S'): 11,
  (35, 'T'): 11,
  (35, 'U'): 11,
  (35, 'V'): 11,
  (35, 'W'): 11,
  (35, 'X'): 11,
  (35, 'Y'): 11,
  (35, 'Z'): 11,
  (35, '_'): 11,
  (35, 'a'): 11,
  (35, 'b'): 11,
  (35, 'c'): 11,
  (35, 'd'): 11,
  (35, 'e'): 37,
  (35, 'f'): 11,
  (35, 'g'): 11,
  (35, 'h'): 11,
  (35, 'i'): 11,
  (35, 'j'): 11,
  (35, 'k'): 11,
  (35, 'l'): 11,
  (35, 'm'): 11,
  (35, 'n'): 11,
  (35, 'o'): 38,
  (35, 'p'): 11,
  (35, 'q'): 11,
  (35, 'r'): 11,
  (35, 's'): 11,
  (35, 't'): 11,
  (35, 'u'): 39,
  (35, 'v'): 11,
  (35, 'w'): 11,
  (35, 'x'): 11,
  (35, 'y'): 11,
  (35, 'z'): 11,
  (37, '0'): 11,
  (37, '1'): 11,
  (37, '2'): 11,
  (37, '3'): 11,
  (37, '4'): 11,
  (37, '5'): 11,
  (37, '6'): 11,
  (37, '7'): 11,
  (37, '8'): 11,
  (37, '9'): 11,
  (37, 'A'): 11,
  (37, 'B'): 11,
  (37, 'C'): 11,
  (37, 'D'): 11,
  (37, 'E'): 11,
  (37, 'F'): 11,
  (37, 'G'): 11,
  (37, 'H'): 11,
  (37, 'I'): 11,
  (37, 'J'): 11,
  (37, 'K'): 11,
  (37, 'L'): 11,
  (37, 'M'): 11,
  (37, 'N'): 11,
  (37, 'O'): 11,
  (37, 'P'): 11,
  (37, 'Q'): 11,
  (37, 'R'): 11,
  (37, 'S'): 11,
  (37, 'T'): 11,
  (37, 'U'): 11,
  (37, 'V'): 11,
  (37, 'W'): 11,
  (37, 'X'): 11,
  (37, 'Y'): 11,
  (37, 'Z'): 11,
  (37, '_'): 11,
  (37, 'a'): 11,
  (37, 'b'): 11,
  (37, 'c'): 11,
  (37, 'd'): 11,
  (37, 'e'): 11,
  (37, 'f'): 11,
  (37, 'g'): 11,
  (37, 'h'): 11,
  (37, 'i'): 11,
  (37, 'j'): 11,
  (37, 'k'): 11,
  (37, 'l'): 11,
  (37, 'm'): 11,
  (37, 'n'): 11,
  (37, 'o'): 11,
  (37, 'p'): 11,
  (37, 'q'): 11,
  (37, 'r'): 11,
  (37, 's'): 11,
  (37, 't'): 63,
  (37, 'u'): 11,
  (37, 'v'): 11,
  (37, 'w'): 11,
  (37, 'x'): 11,
  (37, 'y'): 11,
  (37, 'z'): 11,
  (38, '0'): 11,
  (38, '1'): 11,
  (38, '2'): 11,
  (38, '3'): 11,
  (38, '4'): 11,
  (38, '5'): 11,
  (38, '6'): 11,
  (38, '7'): 11,
  (38, '8'): 11,
  (38, '9'): 11,
  (38, 'A'): 11,
  (38, 'B'): 11,
  (38, 'C'): 11,
  (38, 'D'): 11,
  (38, 'E'): 11,
  (38, 'F'): 11,
  (38, 'G'): 11,
  (38, 'H'): 11,
  (38, 'I'): 11,
  (38, 'J'): 11,
  (38, 'K'): 11,
  (38, 'L'): 11,
  (38, 'M'): 11,
  (38, 'N'): 11,
  (38, 'O'): 11,
  (38, 'P'): 11,
  (38, 'Q'): 11,
  (38, 'R'): 11,
  (38, 'S'): 11,
  (38, 'T'): 11,
  (38, 'U'): 11,
  (38, 'V'): 11,
  (38, 'W'): 11,
  (38, 'X'): 11,
  (38, 'Y'): 11,
  (38, 'Z'): 11,
  (38, '_'): 11,
  (38, 'a'): 11,
  (38, 'b'): 11,
  (38, 'c'): 11,
  (38, 'd'): 47,
  (38, 'e'): 11,
  (38, 'f'): 11,
  (38, 'g'): 11,
  (38, 'h'): 11,
  (38, 'i'): 11,
  (38, 'j'): 11,
  (38, 'k'): 11,
  (38, 'l'): 11,
  (38, 'm'): 11,
  (38, 'n'): 11,
  (38, 'o'): 11,
  (38, 'p'): 11,
  (38, 'q'): 11,
  (38, 'r'): 11,
  (38, 's'): 11,
  (38, 't'): 11,
  (38, 'u'): 11,
  (38, 'v'): 11,
  (38, 'w'): 11,
  (38, 'x'): 11,
  (38, 'y'): 11,
  (38, 'z'): 11,
  (39, '0'): 11,
  (39, '1'): 11,
  (39, '2'): 11,
  (39, '3'): 11,
  (39, '4'): 11,
  (39, '5'): 11,
  (39, '6'): 11,
  (39, '7'): 11,
  (39, '8'): 11,
  (39, '9'): 11,
  (39, 'A'): 11,
  (39, 'B'): 11,
  (39, 'C'): 11,
  (39, 'D'): 11,
  (39, 'E'): 11,
  (39, 'F'): 11,
  (39, 'G'): 11,
  (39, 'H'): 11,
  (39, 'I'): 11,
  (39, 'J'): 11,
  (39, 'K'): 11,
  (39, 'L'): 11,
  (39, 'M'): 11,
  (39, 'N'): 11,
  (39, 'O'): 11,
  (39, 'P'): 11,
  (39, 'Q'): 11,
  (39, 'R'): 11,
  (39, 'S'): 11,
  (39, 'T'): 11,
  (39, 'U'): 11,
  (39, 'V'): 11,
  (39, 'W'): 11,
  (39, 'X'): 11,
  (39, 'Y'): 11,
  (39, 'Z'): 11,
  (39, '_'): 11,
  (39, 'a'): 11,
  (39, 'b'): 11,
  (39, 'c'): 11,
  (39, 'd'): 11,
  (39, 'e'): 11,
  (39, 'f'): 11,
  (39, 'g'): 11,
  (39, 'h'): 11,
  (39, 'i'): 11,
  (39, 'j'): 11,
  (39, 'k'): 11,
  (39, 'l'): 40,
  (39, 'm'): 11,
  (39, 'n'): 11,
  (39, 'o'): 11,
  (39, 'p'): 11,
  (39, 'q'): 11,
  (39, 'r'): 11,
  (39, 's'): 11,
  (39, 't'): 11,
  (39, 'u'): 11,
  (39, 'v'): 11,
  (39, 'w'): 11,
  (39, 'x'): 11,
  (39, 'y'): 11,
  (39, 'z'): 11,
  (40, '0'): 11,
  (40, '1'): 11,
  (40, '2'): 11,
  (40, '3'): 11,
  (40, '4'): 11,
  (40, '5'): 11,
  (40, '6'): 11,
  (40, '7'): 11,
  (40, '8'): 11,
  (40, '9'): 11,
  (40, 'A'): 11,
  (40, 'B'): 11,
  (40, 'C'): 11,
  (40, 'D'): 11,
  (40, 'E'): 11,
  (40, 'F'): 11,
  (40, 'G'): 11,
  (40, 'H'): 11,
  (40, 'I'): 11,
  (40, 'J'): 11,
  (40, 'K'): 11,
  (40, 'L'): 11,
  (40, 'M'): 11,
  (40, 'N'): 11,
  (40, 'O'): 11,
  (40, 'P'): 11,
  (40, 'Q'): 11,
  (40, 'R'): 11,
  (40, 'S'): 11,
  (40, 'T'): 11,
  (40, 'U'): 11,
  (40, 'V'): 11,
  (40, 'W'): 11,
  (40, 'X'): 11,
  (40, 'Y'): 11,
  (40, 'Z'): 11,
  (40, '_'): 11,
  (40, 'a'): 11,
  (40, 'b'): 11,
  (40, 'c'): 11,
  (40, 'd'): 11,
  (40, 'e'): 11,
  (40, 'f'): 11,
  (40, 'g'): 11,
  (40, 'h'): 11,
  (40, 'i'): 11,
  (40, 'j'): 11,
  (40, 'k'): 11,
  (40, 'l'): 11,
  (40, 'm'): 11,
  (40, 'n'): 11,
  (40, 'o'): 11,
  (40, 'p'): 11,
  (40, 'q'): 11,
  (40, 'r'): 11,
  (40, 's'): 11,
  (40, 't'): 41,
  (40, 'u'): 11,
  (40, 'v'): 11,
  (40, 'w'): 11,
  (40, 'x'): 11,
  (40, 'y'): 11,
  (40, 'z'): 11,
  (41, '0'): 11,
  (41, '1'): 11,
  (41, '2'): 11,
  (41, '3'): 11,
  (41, '4'): 11,
  (41, '5'): 11,
  (41, '6'): 11,
  (41, '7'): 11,
  (41, '8'): 11,
  (41, '9'): 11,
  (41, 'A'): 11,
  (41, 'B'): 11,
  (41, 'C'): 11,
  (41, 'D'): 11,
  (41, 'E'): 11,
  (41, 'F'): 11,
  (41, 'G'): 11,
  (41, 'H'): 11,
  (41, 'I'): 11,
  (41, 'J'): 11,
  (41, 'K'): 11,
  (41, 'L'): 11,
  (41, 'M'): 11,
  (41, 'N'): 11,
  (41, 'O'): 11,
  (41, 'P'): 11,
  (41, 'Q'): 11,
  (41, 'R'): 11,
  (41, 'S'): 11,
  (41, 'T'): 11,
  (41, 'U'): 11,
  (41, 'V'): 11,
  (41, 'W'): 11,
  (41, 'X'): 11,
  (41, 'Y'): 11,
  (41, 'Z'): 11,
  (41, '_'): 11,
  (41, 'a'): 11,
  (41, 'b'): 11,
  (41, 'c'): 11,
  (41, 'd'): 11,
  (41, 'e'): 11,
  (41, 'f'): 11,
  (41, 'g'): 11,
  (41, 'h'): 11,
  (41, 'i'): 42,
  (41, 'j'): 11,
  (41, 'k'): 11,
  (41, 'l'): 11,
  (41, 'm'): 11,
  (41, 'n'): 11,
  (41, 'o'): 11,
  (41, 'p'): 11,
  (41, 'q'): 11,
  (41, 'r'): 11,
  (41, 's'): 11,
  (41, 't'): 11,
  (41, 'u'): 11,
  (41, 'v'): 11,
  (41, 'w'): 11,
  (41, 'x'): 11,
  (41, 'y'): 11,
  (41, 'z'): 11,
  (42, '0'): 11,
  (42, '1'): 11,
  (42, '2'): 11,
  (42, '3'): 11,
  (42, '4'): 11,
  (42, '5'): 11,
  (42, '6'): 11,
  (42, '7'): 11,
  (42, '8'): 11,
  (42, '9'): 11,
  (42, 'A'): 11,
  (42, 'B'): 11,
  (42, 'C'): 11,
  (42, 'D'): 11,
  (42, 'E'): 11,
  (42, 'F'): 11,
  (42, 'G'): 11,
  (42, 'H'): 11,
  (42, 'I'): 11,
  (42, 'J'): 11,
  (42, 'K'): 11,
  (42, 'L'): 11,
  (42, 'M'): 11,
  (42, 'N'): 11,
  (42, 'O'): 11,
  (42, 'P'): 11,
  (42, 'Q'): 11,
  (42, 'R'): 11,
  (42, 'S'): 11,
  (42, 'T'): 11,
  (42, 'U'): 11,
  (42, 'V'): 11,
  (42, 'W'): 11,
  (42, 'X'): 11,
  (42, 'Y'): 11,
  (42, 'Z'): 11,
  (42, '_'): 11,
  (42, 'a'): 11,
  (42, 'b'): 11,
  (42, 'c'): 11,
  (42, 'd'): 11,
  (42, 'e'): 11,
  (42, 'f'): 43,
  (42, 'g'): 11,
  (42, 'h'): 11,
  (42, 'i'): 11,
  (42, 'j'): 11,
  (42, 'k'): 11,
  (42, 'l'): 11,
  (42, 'm'): 11,
  (42, 'n'): 11,
  (42, 'o'): 11,
  (42, 'p'): 11,
  (42, 'q'): 11,
  (42, 'r'): 11,
  (42, 's'): 11,
  (42, 't'): 11,
  (42, 'u'): 11,
  (42, 'v'): 11,
  (42, 'w'): 11,
  (42, 'x'): 11,
  (42, 'y'): 11,
  (42, 'z'): 11,
  (43, '0'): 11,
  (43, '1'): 11,
  (43, '2'): 11,
  (43, '3'): 11,
  (43, '4'): 11,
  (43, '5'): 11,
  (43, '6'): 11,
  (43, '7'): 11,
  (43, '8'): 11,
  (43, '9'): 11,
  (43, 'A'): 11,
  (43, 'B'): 11,
  (43, 'C'): 11,
  (43, 'D'): 11,
  (43, 'E'): 11,
  (43, 'F'): 11,
  (43, 'G'): 11,
  (43, 'H'): 11,
  (43, 'I'): 11,
  (43, 'J'): 11,
  (43, 'K'): 11,
  (43, 'L'): 11,
  (43, 'M'): 11,
  (43, 'N'): 11,
  (43, 'O'): 11,
  (43, 'P'): 11,
  (43, 'Q'): 11,
  (43, 'R'): 11,
  (43, 'S'): 11,
  (43, 'T'): 11,
  (43, 'U'): 11,
  (43, 'V'): 11,
  (43, 'W'): 11,
  (43, 'X'): 11,
  (43, 'Y'): 11,
  (43, 'Z'): 11,
  (43, '_'): 11,
  (43, 'a'): 11,
  (43, 'b'): 11,
  (43, 'c'): 11,
  (43, 'd'): 11,
  (43, 'e'): 11,
  (43, 'f'): 11,
  (43, 'g'): 11,
  (43, 'h'): 11,
  (43, 'i'): 44,
  (43, 'j'): 11,
  (43, 'k'): 11,
  (43, 'l'): 11,
  (43, 'm'): 11,
  (43, 'n'): 11,
  (43, 'o'): 11,
  (43, 'p'): 11,
  (43, 'q'): 11,
  (43, 'r'): 11,
  (43, 's'): 11,
  (43, 't'): 11,
  (43, 'u'): 11,
  (43, 'v'): 11,
  (43, 'w'): 11,
  (43, 'x'): 11,
  (43, 'y'): 11,
  (43, 'z'): 11,
  (44, '0'): 11,
  (44, '1'): 11,
  (44, '2'): 11,
  (44, '3'): 11,
  (44, '4'): 11,
  (44, '5'): 11,
  (44, '6'): 11,
  (44, '7'): 11,
  (44, '8'): 11,
  (44, '9'): 11,
  (44, 'A'): 11,
  (44, 'B'): 11,
  (44, 'C'): 11,
  (44, 'D'): 11,
  (44, 'E'): 11,
  (44, 'F'): 11,
  (44, 'G'): 11,
  (44, 'H'): 11,
  (44, 'I'): 11,
  (44, 'J'): 11,
  (44, 'K'): 11,
  (44, 'L'): 11,
  (44, 'M'): 11,
  (44, 'N'): 11,
  (44, 'O'): 11,
  (44, 'P'): 11,
  (44, 'Q'): 11,
  (44, 'R'): 11,
  (44, 'S'): 11,
  (44, 'T'): 11,
  (44, 'U'): 11,
  (44, 'V'): 11,
  (44, 'W'): 11,
  (44, 'X'): 11,
  (44, 'Y'): 11,
  (44, 'Z'): 11,
  (44, '_'): 11,
  (44, 'a'): 11,
  (44, 'b'): 11,
  (44, 'c'): 11,
  (44, 'd'): 11,
  (44, 'e'): 11,
  (44, 'f'): 11,
  (44, 'g'): 11,
  (44, 'h'): 11,
  (44, 'i'): 11,
  (44, 'j'): 11,
  (44, 'k'): 11,
  (44, 'l'): 45,
  (44, 'm'): 11,
  (44, 'n'): 11,
  (44, 'o'): 11,
  (44, 'p'): 11,
  (44, 'q'): 11,
  (44, 'r'): 11,
  (44, 's'): 11,
  (44, 't'): 11,
  (44, 'u'): 11,
  (44, 'v'): 11,
  (44, 'w'): 11,
  (44, 'x'): 11,
  (44, 'y'): 11,
  (44, 'z'): 11,
  (45, '0'): 11,
  (45, '1'): 11,
  (45, '2'): 11,
  (45, '3'): 11,
  (45, '4'): 11,
  (45, '5'): 11,
  (45, '6'): 11,
  (45, '7'): 11,
  (45, '8'): 11,
  (45, '9'): 11,
  (45, 'A'): 11,
  (45, 'B'): 11,
  (45, 'C'): 11,
  (45, 'D'): 11,
  (45, 'E'): 11,
  (45, 'F'): 11,
  (45, 'G'): 11,
  (45, 'H'): 11,
  (45, 'I'): 11,
  (45, 'J'): 11,
  (45, 'K'): 11,
  (45, 'L'): 11,
  (45, 'M'): 11,
  (45, 'N'): 11,
  (45, 'O'): 11,
  (45, 'P'): 11,
  (45, 'Q'): 11,
  (45, 'R'): 11,
  (45, 'S'): 11,
  (45, 'T'): 11,
  (45, 'U'): 11,
  (45, 'V'): 11,
  (45, 'W'): 11,
  (45, 'X'): 11,
  (45, 'Y'): 11,
  (45, 'Z'): 11,
  (45, '_'): 11,
  (45, 'a'): 11,
  (45, 'b'): 11,
  (45, 'c'): 11,
  (45, 'd'): 11,
  (45, 'e'): 46,
  (45, 'f'): 11,
  (45, 'g'): 11,
  (45, 'h'): 11,
  (45, 'i'): 11,
  (45, 'j'): 11,
  (45, 'k'): 11,
  (45, 'l'): 11,
  (45, 'm'): 11,
  (45, 'n'): 11,
  (45, 'o'): 11,
  (45, 'p'): 11,
  (45, 'q'): 11,
  (45, 'r'): 11,
  (45, 's'): 11,
  (45, 't'): 11,
  (45, 'u'): 11,
  (45, 'v'): 11,
  (45, 'w'): 11,
  (45, 'x'): 11,
  (45, 'y'): 11,
  (45, 'z'): 11,
  (46, '0'): 11,
  (46, '1'): 11,
  (46, '2'): 11,
  (46, '3'): 11,
  (46, '4'): 11,
  (46, '5'): 11,
  (46, '6'): 11,
  (46, '7'): 11,
  (46, '8'): 11,
  (46, '9'): 11,
  (46, 'A'): 11,
  (46, 'B'): 11,
  (46, 'C'): 11,
  (46, 'D'): 11,
  (46, 'E'): 11,
  (46, 'F'): 11,
  (46, 'G'): 11,
  (46, 'H'): 11,
  (46, 'I'): 11,
  (46, 'J'): 11,
  (46, 'K'): 11,
  (46, 'L'): 11,
  (46, 'M'): 11,
  (46, 'N'): 11,
  (46, 'O'): 11,
  (46, 'P'): 11,
  (46, 'Q'): 11,
  (46, 'R'): 11,
  (46, 'S'): 11,
  (46, 'T'): 11,
  (46, 'U'): 11,
  (46, 'V'): 11,
  (46, 'W'): 11,
  (46, 'X'): 11,
  (46, 'Y'): 11,
  (46, 'Z'): 11,
  (46, '_'): 11,
  (46, 'a'): 11,
  (46, 'b'): 11,
  (46, 'c'): 11,
  (46, 'd'): 11,
  (46, 'e'): 11,
  (46, 'f'): 11,
  (46, 'g'): 11,
  (46, 'h'): 11,
  (46, 'i'): 11,
  (46, 'j'): 11,
  (46, 'k'): 11,
  (46, 'l'): 11,
  (46, 'm'): 11,
  (46, 'n'): 11,
  (46, 'o'): 11,
  (46, 'p'): 11,
  (46, 'q'): 11,
  (46, 'r'): 11,
  (46, 's'): 11,
  (46, 't'): 11,
  (46, 'u'): 11,
  (46, 'v'): 11,
  (46, 'w'): 11,
  (46, 'x'): 11,
  (46, 'y'): 11,
  (46, 'z'): 11,
  (47, '0'): 11,
  (47, '1'): 11,
  (47, '2'): 11,
  (47, '3'): 11,
  (47, '4'): 11,
  (47, '5'): 11,
  (47, '6'): 11,
  (47, '7'): 11,
  (47, '8'): 11,
  (47, '9'): 11,
  (47, 'A'): 11,
  (47, 'B'): 11,
  (47, 'C'): 11,
  (47, 'D'): 11,
  (47, 'E'): 11,
  (47, 'F'): 11,
  (47, 'G'): 11,
  (47, 'H'): 11,
  (47, 'I'): 11,
  (47, 'J'): 11,
  (47, 'K'): 11,
  (47, 'L'): 11,
  (47, 'M'): 11,
  (47, 'N'): 11,
  (47, 'O'): 11,
  (47, 'P'): 11,
  (47, 'Q'): 11,
  (47, 'R'): 11,
  (47, 'S'): 11,
  (47, 'T'): 11,
  (47, 'U'): 11,
  (47, 'V'): 11,
  (47, 'W'): 11,
  (47, 'X'): 11,
  (47, 'Y'): 11,
  (47, 'Z'): 11,
  (47, '_'): 11,
  (47, 'a'): 11,
  (47, 'b'): 11,
  (47, 'c'): 11,
  (47, 'd'): 11,
  (47, 'e'): 11,
  (47, 'f'): 11,
  (47, 'g'): 11,
  (47, 'h'): 11,
  (47, 'i'): 11,
  (47, 'j'): 11,
  (47, 'k'): 11,
  (47, 'l'): 11,
  (47, 'm'): 11,
  (47, 'n'): 11,
  (47, 'o'): 11,
  (47, 'p'): 11,
  (47, 'q'): 11,
  (47, 'r'): 11,
  (47, 's'): 11,
  (47, 't'): 11,
  (47, 'u'): 48,
  (47, 'v'): 11,
  (47, 'w'): 11,
  (47, 'x'): 11,
  (47, 'y'): 11,
  (47, 'z'): 11,
  (48, '0'): 11,
  (48, '1'): 11,
  (48, '2'): 11,
  (48, '3'): 11,
  (48, '4'): 11,
  (48, '5'): 11,
  (48, '6'): 11,
  (48, '7'): 11,
  (48, '8'): 11,
  (48, '9'): 11,
  (48, 'A'): 11,
  (48, 'B'): 11,
  (48, 'C'): 11,
  (48, 'D'): 11,
  (48, 'E'): 11,
  (48, 'F'): 11,
  (48, 'G'): 11,
  (48, 'H'): 11,
  (48, 'I'): 11,
  (48, 'J'): 11,
  (48, 'K'): 11,
  (48, 'L'): 11,
  (48, 'M'): 11,
  (48, 'N'): 11,
  (48, 'O'): 11,
  (48, 'P'): 11,
  (48, 'Q'): 11,
  (48, 'R'): 11,
  (48, 'S'): 11,
  (48, 'T'): 11,
  (48, 'U'): 11,
  (48, 'V'): 11,
  (48, 'W'): 11,
  (48, 'X'): 11,
  (48, 'Y'): 11,
  (48, 'Z'): 11,
  (48, '_'): 11,
  (48, 'a'): 11,
  (48, 'b'): 11,
  (48, 'c'): 11,
  (48, 'd'): 11,
  (48, 'e'): 11,
  (48, 'f'): 11,
  (48, 'g'): 11,
  (48, 'h'): 11,
  (48, 'i'): 11,
  (48, 'j'): 11,
  (48, 'k'): 11,
  (48, 'l'): 49,
  (48, 'm'): 11,
  (48, 'n'): 11,
  (48, 'o'): 11,
  (48, 'p'): 11,
  (48, 'q'): 11,
  (48, 'r'): 11,
  (48, 's'): 11,
  (48, 't'): 11,
  (48, 'u'): 11,
  (48, 'v'): 11,
  (48, 'w'): 11,
  (48, 'x'): 11,
  (48, 'y'): 11,
  (48, 'z'): 11,
  (49, '0'): 11,
  (49, '1'): 11,
  (49, '2'): 11,
  (49, '3'): 11,
  (49, '4'): 11,
  (49, '5'): 11,
  (49, '6'): 11,
  (49, '7'): 11,
  (49, '8'): 11,
  (49, '9'): 11,
  (49, 'A'): 11,
  (49, 'B'): 11,
  (49, 'C'): 11,
  (49, 'D'): 11,
  (49, 'E'): 11,
  (49, 'F'): 11,
  (49, 'G'): 11,
  (49, 'H'): 11,
  (49, 'I'): 11,
  (49, 'J'): 11,
  (49, 'K'): 11,
  (49, 'L'): 11,
  (49, 'M'): 11,
  (49, 'N'): 11,
  (49, 'O'): 11,
  (49, 'P'): 11,
  (49, 'Q'): 11,
  (49, 'R'): 11,
  (49, 'S'): 11,
  (49, 'T'): 11,
  (49, 'U'): 11,
  (49, 'V'): 11,
  (49, 'W'): 11,
  (49, 'X'): 11,
  (49, 'Y'): 11,
  (49, 'Z'): 11,
  (49, '_'): 11,
  (49, 'a'): 11,
  (49, 'b'): 11,
  (49, 'c'): 11,
  (49, 'd'): 11,
  (49, 'e'): 50,
  (49, 'f'): 11,
  (49, 'g'): 11,
  (49, 'h'): 11,
  (49, 'i'): 11,
  (49, 'j'): 11,
  (49, 'k'): 11,
  (49, 'l'): 11,
  (49, 'm'): 11,
  (49, 'n'): 11,
  (49, 'o'): 11,
  (49, 'p'): 11,
  (49, 'q'): 11,
  (49, 'r'): 11,
  (49, 's'): 11,
  (49, 't'): 11,
  (49, 'u'): 11,
  (49, 'v'): 11,
  (49, 'w'): 11,
  (49, 'x'): 11,
  (49, 'y'): 11,
  (49, 'z'): 11,
  (50, '0'): 11,
  (50, '1'): 11,
  (50, '2'): 11,
  (50, '3'): 11,
  (50, '4'): 11,
  (50, '5'): 11,
  (50, '6'): 11,
  (50, '7'): 11,
  (50, '8'): 11,
  (50, '9'): 11,
  (50, 'A'): 11,
  (50, 'B'): 11,
  (50, 'C'): 11,
  (50, 'D'): 11,
  (50, 'E'): 11,
  (50, 'F'): 11,
  (50, 'G'): 11,
  (50, 'H'): 11,
  (50, 'I'): 11,
  (50, 'J'): 11,
  (50, 'K'): 11,
  (50, 'L'): 11,
  (50, 'M'): 11,
  (50, 'N'): 11,
  (50, 'O'): 11,
  (50, 'P'): 11,
  (50, 'Q'): 11,
  (50, 'R'): 11,
  (50, 'S'): 11,
  (50, 'T'): 11,
  (50, 'U'): 11,
  (50, 'V'): 11,
  (50, 'W'): 11,
  (50, 'X'): 11,
  (50, 'Y'): 11,
  (50, 'Z'): 11,
  (50, '_'): 51,
  (50, 'a'): 11,
  (50, 'b'): 11,
  (50, 'c'): 11,
  (50, 'd'): 11,
  (50, 'e'): 11,
  (50, 'f'): 11,
  (50, 'g'): 11,
  (50, 'h'): 11,
  (50, 'i'): 11,
  (50, 'j'): 11,
  (50, 'k'): 11,
  (50, 'l'): 11,
  (50, 'm'): 11,
  (50, 'n'): 11,
  (50, 'o'): 11,
  (50, 'p'): 11,
  (50, 'q'): 11,
  (50, 'r'): 11,
  (50, 's'): 11,
  (50, 't'): 11,
  (50, 'u'): 11,
  (50, 'v'): 11,
  (50, 'w'): 11,
  (50, 'x'): 11,
  (50, 'y'): 11,
  (50, 'z'): 11,
  (51, '0'): 11,
  (51, '1'): 11,
  (51, '2'): 11,
  (51, '3'): 11,
  (51, '4'): 11,
  (51, '5'): 11,
  (51, '6'): 11,
  (51, '7'): 11,
  (51, '8'): 11,
  (51, '9'): 11,
  (51, 'A'): 11,
  (51, 'B'): 11,
  (51, 'C'): 11,
  (51, 'D'): 11,
  (51, 'E'): 11,
  (51, 'F'): 11,
  (51, 'G'): 11,
  (51, 'H'): 11,
  (51, 'I'): 11,
  (51, 'J'): 11,
  (51, 'K'): 11,
  (51, 'L'): 11,
  (51, 'M'): 11,
  (51, 'N'): 11,
  (51, 'O'): 11,
  (51, 'P'): 11,
  (51, 'Q'): 11,
  (51, 'R'): 11,
  (51, 'S'): 11,
  (51, 'T'): 11,
  (51, 'U'): 11,
  (51, 'V'): 11,
  (51, 'W'): 11,
  (51, 'X'): 11,
  (51, 'Y'): 11,
  (51, 'Z'): 11,
  (51, '_'): 11,
  (51, 'a'): 11,
  (51, 'b'): 11,
  (51, 'c'): 11,
  (51, 'd'): 11,
  (51, 'e'): 11,
  (51, 'f'): 11,
  (51, 'g'): 11,
  (51, 'h'): 11,
  (51, 'i'): 11,
  (51, 'j'): 11,
  (51, 'k'): 11,
  (51, 'l'): 11,
  (51, 'm'): 11,
  (51, 'n'): 11,
  (51, 'o'): 11,
  (51, 'p'): 11,
  (51, 'q'): 11,
  (51, 'r'): 11,
  (51, 's'): 11,
  (51, 't'): 52,
  (51, 'u'): 11,
  (51, 'v'): 11,
  (51, 'w'): 11,
  (51, 'x'): 11,
  (51, 'y'): 11,
  (51, 'z'): 11,
  (52, '0'): 11,
  (52, '1'): 11,
  (52, '2'): 11,
  (52, '3'): 11,
  (52, '4'): 11,
  (52, '5'): 11,
  (52, '6'): 11,
  (52, '7'): 11,
  (52, '8'): 11,
  (52, '9'): 11,
  (52, 'A'): 11,
  (52, 'B'): 11,
  (52, 'C'): 11,
  (52, 'D'): 11,
  (52, 'E'): 11,
  (52, 'F'): 11,
  (52, 'G'): 11,
  (52, 'H'): 11,
  (52, 'I'): 11,
  (52, 'J'): 11,
  (52, 'K'): 11,
  (52, 'L'): 11,
  (52, 'M'): 11,
  (52, 'N'): 11,
  (52, 'O'): 11,
  (52, 'P'): 11,
  (52, 'Q'): 11,
  (52, 'R'): 11,
  (52, 'S'): 11,
  (52, 'T'): 11,
  (52, 'U'): 11,
  (52, 'V'): 11,
  (52, 'W'): 11,
  (52, 'X'): 11,
  (52, 'Y'): 11,
  (52, 'Z'): 11,
  (52, '_'): 11,
  (52, 'a'): 11,
  (52, 'b'): 11,
  (52, 'c'): 11,
  (52, 'd'): 11,
  (52, 'e'): 11,
  (52, 'f'): 11,
  (52, 'g'): 11,
  (52, 'h'): 11,
  (52, 'i'): 11,
  (52, 'j'): 11,
  (52, 'k'): 11,
  (52, 'l'): 11,
  (52, 'm'): 11,
  (52, 'n'): 11,
  (52, 'o'): 11,
  (52, 'p'): 11,
  (52, 'q'): 11,
  (52, 'r'): 53,
  (52, 's'): 11,
  (52, 't'): 11,
  (52, 'u'): 11,
  (52, 'v'): 11,
  (52, 'w'): 11,
  (52, 'x'): 11,
  (52, 'y'): 11,
  (52, 'z'): 11,
  (53, '0'): 11,
  (53, '1'): 11,
  (53, '2'): 11,
  (53, '3'): 11,
  (53, '4'): 11,
  (53, '5'): 11,
  (53, '6'): 11,
  (53, '7'): 11,
  (53, '8'): 11,
  (53, '9'): 11,
  (53, 'A'): 11,
  (53, 'B'): 11,
  (53, 'C'): 11,
  (53, 'D'): 11,
  (53, 'E'): 11,
  (53, 'F'): 11,
  (53, 'G'): 11,
  (53, 'H'): 11,
  (53, 'I'): 11,
  (53, 'J'): 11,
  (53, 'K'): 11,
  (53, 'L'): 11,
  (53, 'M'): 11,
  (53, 'N'): 11,
  (53, 'O'): 11,
  (53, 'P'): 11,
  (53, 'Q'): 11,
  (53, 'R'): 11,
  (53, 'S'): 11,
  (53, 'T'): 11,
  (53, 'U'): 11,
  (53, 'V'): 11,
  (53, 'W'): 11,
  (53, 'X'): 11,
  (53, 'Y'): 11,
  (53, 'Z'): 11,
  (53, '_'): 11,
  (53, 'a'): 54,
  (53, 'b'): 11,
  (53, 'c'): 11,
  (53, 'd'): 11,
  (53, 'e'): 11,
  (53, 'f'): 11,
  (53, 'g'): 11,
  (53, 'h'): 11,
  (53, 'i'): 11,
  (53, 'j'): 11,
  (53, 'k'): 11,
  (53, 'l'): 11,
  (53, 'm'): 11,
  (53, 'n'): 11,
  (53, 'o'): 11,
  (53, 'p'): 11,
  (53, 'q'): 11,
  (53, 'r'): 11,
  (53, 's'): 11,
  (53, 't'): 11,
  (53, 'u'): 11,
  (53, 'v'): 11,
  (53, 'w'): 11,
  (53, 'x'): 11,
  (53, 'y'): 11,
  (53, 'z'): 11,
  (54, '0'): 11,
  (54, '1'): 11,
  (54, '2'): 11,
  (54, '3'): 11,
  (54, '4'): 11,
  (54, '5'): 11,
  (54, '6'): 11,
  (54, '7'): 11,
  (54, '8'): 11,
  (54, '9'): 11,
  (54, 'A'): 11,
  (54, 'B'): 11,
  (54, 'C'): 11,
  (54, 'D'): 11,
  (54, 'E'): 11,
  (54, 'F'): 11,
  (54, 'G'): 11,
  (54, 'H'): 11,
  (54, 'I'): 11,
  (54, 'J'): 11,
  (54, 'K'): 11,
  (54, 'L'): 11,
  (54, 'M'): 11,
  (54, 'N'): 11,
  (54, 'O'): 11,
  (54, 'P'): 11,
  (54, 'Q'): 11,
  (54, 'R'): 11,
  (54, 'S'): 11,
  (54, 'T'): 11,
  (54, 'U'): 11,
  (54, 'V'): 11,
  (54, 'W'): 11,
  (54, 'X'): 11,
  (54, 'Y'): 11,
  (54, 'Z'): 11,
  (54, '_'): 11,
  (54, 'a'): 11,
  (54, 'b'): 11,
  (54, 'c'): 11,
  (54, 'd'): 11,
  (54, 'e'): 11,
  (54, 'f'): 11,
  (54, 'g'): 11,
  (54, 'h'): 11,
  (54, 'i'): 11,
  (54, 'j'): 11,
  (54, 'k'): 11,
  (54, 'l'): 11,
  (54, 'm'): 11,
  (54, 'n'): 55,
  (54, 'o'): 11,
  (54, 'p'): 11,
  (54, 'q'): 11,
  (54, 'r'): 11,
  (54, 's'): 11,
  (54, 't'): 11,
  (54, 'u'): 11,
  (54, 'v'): 11,
  (54, 'w'): 11,
  (54, 'x'): 11,
  (54, 'y'): 11,
  (54, 'z'): 11,
  (55, '0'): 11,
  (55, '1'): 11,
  (55, '2'): 11,
  (55, '3'): 11,
  (55, '4'): 11,
  (55, '5'): 11,
  (55, '6'): 11,
  (55, '7'): 11,
  (55, '8'): 11,
  (55, '9'): 11,
  (55, 'A'): 11,
  (55, 'B'): 11,
  (55, 'C'): 11,
  (55, 'D'): 11,
  (55, 'E'): 11,
  (55, 'F'): 11,
  (55, 'G'): 11,
  (55, 'H'): 11,
  (55, 'I'): 11,
  (55, 'J'): 11,
  (55, 'K'): 11,
  (55, 'L'): 11,
  (55, 'M'): 11,
  (55, 'N'): 11,
  (55, 'O'): 11,
  (55, 'P'): 11,
  (55, 'Q'): 11,
  (55, 'R'): 11,
  (55, 'S'): 11,
  (55, 'T'): 11,
  (55, 'U'): 11,
  (55, 'V'): 11,
  (55, 'W'): 11,
  (55, 'X'): 11,
  (55, 'Y'): 11,
  (55, 'Z'): 11,
  (55, '_'): 11,
  (55, 'a'): 11,
  (55, 'b'): 11,
  (55, 'c'): 11,
  (55, 'd'): 11,
  (55, 'e'): 11,
  (55, 'f'): 11,
  (55, 'g'): 11,
  (55, 'h'): 11,
  (55, 'i'): 11,
  (55, 'j'): 11,
  (55, 'k'): 11,
  (55, 'l'): 11,
  (55, 'm'): 11,
  (55, 'n'): 11,
  (55, 'o'): 11,
  (55, 'p'): 11,
  (55, 'q'): 11,
  (55, 'r'): 11,
  (55, 's'): 56,
  (55, 't'): 11,
  (55, 'u'): 11,
  (55, 'v'): 11,
  (55, 'w'): 11,
  (55, 'x'): 11,
  (55, 'y'): 11,
  (55, 'z'): 11,
  (56, '0'): 11,
  (56, '1'): 11,
  (56, '2'): 11,
  (56, '3'): 11,
  (56, '4'): 11,
  (56, '5'): 11,
  (56, '6'): 11,
  (56, '7'): 11,
  (56, '8'): 11,
  (56, '9'): 11,
  (56, 'A'): 11,
  (56, 'B'): 11,
  (56, 'C'): 11,
  (56, 'D'): 11,
  (56, 'E'): 11,
  (56, 'F'): 11,
  (56, 'G'): 11,
  (56, 'H'): 11,
  (56, 'I'): 11,
  (56, 'J'): 11,
  (56, 'K'): 11,
  (56, 'L'): 11,
  (56, 'M'): 11,
  (56, 'N'): 11,
  (56, 'O'): 11,
  (56, 'P'): 11,
  (56, 'Q'): 11,
  (56, 'R'): 11,
  (56, 'S'): 11,
  (56, 'T'): 11,
  (56, 'U'): 11,
  (56, 'V'): 11,
  (56, 'W'): 11,
  (56, 'X'): 11,
  (56, 'Y'): 11,
  (56, 'Z'): 11,
  (56, '_'): 11,
  (56, 'a'): 11,
  (56, 'b'): 11,
  (56, 'c'): 11,
  (56, 'd'): 11,
  (56, 'e'): 11,
  (56, 'f'): 11,
  (56, 'g'): 11,
  (56, 'h'): 11,
  (56, 'i'): 11,
  (56, 'j'): 11,
  (56, 'k'): 11,
  (56, 'l'): 11,
  (56, 'm'): 11,
  (56, 'n'): 11,
  (56, 'o'): 11,
  (56, 'p'): 57,
  (56, 'q'): 11,
  (56, 'r'): 11,
  (56, 's'): 11,
  (56, 't'): 11,
  (56, 'u'): 11,
  (56, 'v'): 11,
  (56, 'w'): 11,
  (56, 'x'): 11,
  (56, 'y'): 11,
  (56, 'z'): 11,
  (57, '0'): 11,
  (57, '1'): 11,
  (57, '2'): 11,
  (57, '3'): 11,
  (57, '4'): 11,
  (57, '5'): 11,
  (57, '6'): 11,
  (57, '7'): 11,
  (57, '8'): 11,
  (57, '9'): 11,
  (57, 'A'): 11,
  (57, 'B'): 11,
  (57, 'C'): 11,
  (57, 'D'): 11,
  (57, 'E'): 11,
  (57, 'F'): 11,
  (57, 'G'): 11,
  (57, 'H'): 11,
  (57, 'I'): 11,
  (57, 'J'): 11,
  (57, 'K'): 11,
  (57, 'L'): 11,
  (57, 'M'): 11,
  (57, 'N'): 11,
  (57, 'O'): 11,
  (57, 'P'): 11,
  (57, 'Q'): 11,
  (57, 'R'): 11,
  (57, 'S'): 11,
  (57, 'T'): 11,
  (57, 'U'): 11,
  (57, 'V'): 11,
  (57, 'W'): 11,
  (57, 'X'): 11,
  (57, 'Y'): 11,
  (57, 'Z'): 11,
  (57, '_'): 11,
  (57, 'a'): 58,
  (57, 'b'): 11,
  (57, 'c'): 11,
  (57, 'd'): 11,
  (57, 'e'): 11,
  (57, 'f'): 11,
  (57, 'g'): 11,
  (57, 'h'): 11,
  (57, 'i'): 11,
  (57, 'j'): 11,
  (57, 'k'): 11,
  (57, 'l'): 11,
  (57, 'm'): 11,
  (57, 'n'): 11,
  (57, 'o'): 11,
  (57, 'p'): 11,
  (57, 'q'): 11,
  (57, 'r'): 11,
  (57, 's'): 11,
  (57, 't'): 11,
  (57, 'u'): 11,
  (57, 'v'): 11,
  (57, 'w'): 11,
  (57, 'x'): 11,
  (57, 'y'): 11,
  (57, 'z'): 11,
  (58, '0'): 11,
  (58, '1'): 11,
  (58, '2'): 11,
  (58, '3'): 11,
  (58, '4'): 11,
  (58, '5'): 11,
  (58, '6'): 11,
  (58, '7'): 11,
  (58, '8'): 11,
  (58, '9'): 11,
  (58, 'A'): 11,
  (58, 'B'): 11,
  (58, 'C'): 11,
  (58, 'D'): 11,
  (58, 'E'): 11,
  (58, 'F'): 11,
  (58, 'G'): 11,
  (58, 'H'): 11,
  (58, 'I'): 11,
  (58, 'J'): 11,
  (58, 'K'): 11,
  (58, 'L'): 11,
  (58, 'M'): 11,
  (58, 'N'): 11,
  (58, 'O'): 11,
  (58, 'P'): 11,
  (58, 'Q'): 11,
  (58, 'R'): 11,
  (58, 'S'): 11,
  (58, 'T'): 11,
  (58, 'U'): 11,
  (58, 'V'): 11,
  (58, 'W'): 11,
  (58, 'X'): 11,
  (58, 'Y'): 11,
  (58, 'Z'): 11,
  (58, '_'): 11,
  (58, 'a'): 11,
  (58, 'b'): 11,
  (58, 'c'): 11,
  (58, 'd'): 11,
  (58, 'e'): 11,
  (58, 'f'): 11,
  (58, 'g'): 11,
  (58, 'h'): 11,
  (58, 'i'): 11,
  (58, 'j'): 11,
  (58, 'k'): 11,
  (58, 'l'): 11,
  (58, 'm'): 11,
  (58, 'n'): 11,
  (58, 'o'): 11,
  (58, 'p'): 11,
  (58, 'q'): 11,
  (58, 'r'): 59,
  (58, 's'): 11,
  (58, 't'): 11,
  (58, 'u'): 11,
  (58, 'v'): 11,
  (58, 'w'): 11,
  (58, 'x'): 11,
  (58, 'y'): 11,
  (58, 'z'): 11,
  (59, '0'): 11,
  (59, '1'): 11,
  (59, '2'): 11,
  (59, '3'): 11,
  (59, '4'): 11,
  (59, '5'): 11,
  (59, '6'): 11,
  (59, '7'): 11,
  (59, '8'): 11,
  (59, '9'): 11,
  (59, 'A'): 11,
  (59, 'B'): 11,
  (59, 'C'): 11,
  (59, 'D'): 11,
  (59, 'E'): 11,
  (59, 'F'): 11,
  (59, 'G'): 11,
  (59, 'H'): 11,
  (59, 'I'): 11,
  (59, 'J'): 11,
  (59, 'K'): 11,
  (59, 'L'): 11,
  (59, 'M'): 11,
  (59, 'N'): 11,
  (59, 'O'): 11,
  (59, 'P'): 11,
  (59, 'Q'): 11,
  (59, 'R'): 11,
  (59, 'S'): 11,
  (59, 'T'): 11,
  (59, 'U'): 11,
  (59, 'V'): 11,
  (59, 'W'): 11,
  (59, 'X'): 11,
  (59, 'Y'): 11,
  (59, 'Z'): 11,
  (59, '_'): 11,
  (59, 'a'): 11,
  (59, 'b'): 11,
  (59, 'c'): 11,
  (59, 'd'): 11,
  (59, 'e'): 60,
  (59, 'f'): 11,
  (59, 'g'): 11,
  (59, 'h'): 11,
  (59, 'i'): 11,
  (59, 'j'): 11,
  (59, 'k'): 11,
  (59, 'l'): 11,
  (59, 'm'): 11,
  (59, 'n'): 11,
  (59, 'o'): 11,
  (59, 'p'): 11,
  (59, 'q'): 11,
  (59, 'r'): 11,
  (59, 's'): 11,
  (59, 't'): 11,
  (59, 'u'): 11,
  (59, 'v'): 11,
  (59, 'w'): 11,
  (59, 'x'): 11,
  (59, 'y'): 11,
  (59, 'z'): 11,
  (60, '0'): 11,
  (60, '1'): 11,
  (60, '2'): 11,
  (60, '3'): 11,
  (60, '4'): 11,
  (60, '5'): 11,
  (60, '6'): 11,
  (60, '7'): 11,
  (60, '8'): 11,
  (60, '9'): 11,
  (60, 'A'): 11,
  (60, 'B'): 11,
  (60, 'C'): 11,
  (60, 'D'): 11,
  (60, 'E'): 11,
  (60, 'F'): 11,
  (60, 'G'): 11,
  (60, 'H'): 11,
  (60, 'I'): 11,
  (60, 'J'): 11,
  (60, 'K'): 11,
  (60, 'L'): 11,
  (60, 'M'): 11,
  (60, 'N'): 11,
  (60, 'O'): 11,
  (60, 'P'): 11,
  (60, 'Q'): 11,
  (60, 'R'): 11,
  (60, 'S'): 11,
  (60, 'T'): 11,
  (60, 'U'): 11,
  (60, 'V'): 11,
  (60, 'W'): 11,
  (60, 'X'): 11,
  (60, 'Y'): 11,
  (60, 'Z'): 11,
  (60, '_'): 11,
  (60, 'a'): 11,
  (60, 'b'): 11,
  (60, 'c'): 11,
  (60, 'd'): 11,
  (60, 'e'): 11,
  (60, 'f'): 11,
  (60, 'g'): 11,
  (60, 'h'): 11,
  (60, 'i'): 11,
  (60, 'j'): 11,
  (60, 'k'): 11,
  (60, 'l'): 11,
  (60, 'm'): 11,
  (60, 'n'): 61,
  (60, 'o'): 11,
  (60, 'p'): 11,
  (60, 'q'): 11,
  (60, 'r'): 11,
  (60, 's'): 11,
  (60, 't'): 11,
  (60, 'u'): 11,
  (60, 'v'): 11,
  (60, 'w'): 11,
  (60, 'x'): 11,
  (60, 'y'): 11,
  (60, 'z'): 11,
  (61, '0'): 11,
  (61, '1'): 11,
  (61, '2'): 11,
  (61, '3'): 11,
  (61, '4'): 11,
  (61, '5'): 11,
  (61, '6'): 11,
  (61, '7'): 11,
  (61, '8'): 11,
  (61, '9'): 11,
  (61, 'A'): 11,
  (61, 'B'): 11,
  (61, 'C'): 11,
  (61, 'D'): 11,
  (61, 'E'): 11,
  (61, 'F'): 11,
  (61, 'G'): 11,
  (61, 'H'): 11,
  (61, 'I'): 11,
  (61, 'J'): 11,
  (61, 'K'): 11,
  (61, 'L'): 11,
  (61, 'M'): 11,
  (61, 'N'): 11,
  (61, 'O'): 11,
  (61, 'P'): 11,
  (61, 'Q'): 11,
  (61, 'R'): 11,
  (61, 'S'): 11,
  (61, 'T'): 11,
  (61, 'U'): 11,
  (61, 'V'): 11,
  (61, 'W'): 11,
  (61, 'X'): 11,
  (61, 'Y'): 11,
  (61, 'Z'): 11,
  (61, '_'): 11,
  (61, 'a'): 11,
  (61, 'b'): 11,
  (61, 'c'): 11,
  (61, 'd'): 11,
  (61, 'e'): 11,
  (61, 'f'): 11,
  (61, 'g'): 11,
  (61, 'h'): 11,
  (61, 'i'): 11,
  (61, 'j'): 11,
  (61, 'k'): 11,
  (61, 'l'): 11,
  (61, 'm'): 11,
  (61, 'n'): 11,
  (61, 'o'): 11,
  (61, 'p'): 11,
  (61, 'q'): 11,
  (61, 'r'): 11,
  (61, 's'): 11,
  (61, 't'): 62,
  (61, 'u'): 11,
  (61, 'v'): 11,
  (61, 'w'): 11,
  (61, 'x'): 11,
  (61, 'y'): 11,
  (61, 'z'): 11,
  (62, '0'): 11,
  (62, '1'): 11,
  (62, '2'): 11,
  (62, '3'): 11,
  (62, '4'): 11,
  (62, '5'): 11,
  (62, '6'): 11,
  (62, '7'): 11,
  (62, '8'): 11,
  (62, '9'): 11,
  (62, 'A'): 11,
  (62, 'B'): 11,
  (62, 'C'): 11,
  (62, 'D'): 11,
  (62, 'E'): 11,
  (62, 'F'): 11,
  (62, 'G'): 11,
  (62, 'H'): 11,
  (62, 'I'): 11,
  (62, 'J'): 11,
  (62, 'K'): 11,
  (62, 'L'): 11,
  (62, 'M'): 11,
  (62, 'N'): 11,
  (62, 'O'): 11,
  (62, 'P'): 11,
  (62, 'Q'): 11,
  (62, 'R'): 11,
  (62, 'S'): 11,
  (62, 'T'): 11,
  (62, 'U'): 11,
  (62, 'V'): 11,
  (62, 'W'): 11,
  (62, 'X'): 11,
  (62, 'Y'): 11,
  (62, 'Z'): 11,
  (62, '_'): 11,
  (62, 'a'): 11,
  (62, 'b'): 11,
  (62, 'c'): 11,
  (62, 'd'): 11,
  (62, 'e'): 11,
  (62, 'f'): 11,
  (62, 'g'): 11,
  (62, 'h'): 11,
  (62, 'i'): 11,
  (62, 'j'): 11,
  (62, 'k'): 11,
  (62, 'l'): 11,
  (62, 'm'): 11,
  (62, 'n'): 11,
  (62, 'o'): 11,
  (62, 'p'): 11,
  (62, 'q'): 11,
  (62, 'r'): 11,
  (62, 's'): 11,
  (62, 't'): 11,
  (62, 'u'): 11,
  (62, 'v'): 11,
  (62, 'w'): 11,
  (62, 'x'): 11,
  (62, 'y'): 11,
  (62, 'z'): 11,
  (63, '0'): 11,
  (63, '1'): 11,
  (63, '2'): 11,
  (63, '3'): 11,
  (63, '4'): 11,
  (63, '5'): 11,
  (63, '6'): 11,
  (63, '7'): 11,
  (63, '8'): 11,
  (63, '9'): 11,
  (63, 'A'): 11,
  (63, 'B'): 11,
  (63, 'C'): 11,
  (63, 'D'): 11,
  (63, 'E'): 11,
  (63, 'F'): 11,
  (63, 'G'): 11,
  (63, 'H'): 11,
  (63, 'I'): 11,
  (63, 'J'): 11,
  (63, 'K'): 11,
  (63, 'L'): 11,
  (63, 'M'): 11,
  (63, 'N'): 11,
  (63, 'O'): 11,
  (63, 'P'): 11,
  (63, 'Q'): 11,
  (63, 'R'): 11,
  (63, 'S'): 11,
  (63, 'T'): 11,
  (63, 'U'): 11,
  (63, 'V'): 11,
  (63, 'W'): 11,
  (63, 'X'): 11,
  (63, 'Y'): 11,
  (63, 'Z'): 11,
  (63, '_'): 11,
  (63, 'a'): 64,
  (63, 'b'): 11,
  (63, 'c'): 11,
  (63, 'd'): 11,
  (63, 'e'): 11,
  (63, 'f'): 11,
  (63, 'g'): 11,
  (63, 'h'): 11,
  (63, 'i'): 11,
  (63, 'j'): 11,
  (63, 'k'): 11,
  (63, 'l'): 11,
  (63, 'm'): 11,
  (63, 'n'): 11,
  (63, 'o'): 11,
  (63, 'p'): 11,
  (63, 'q'): 11,
  (63, 'r'): 11,
  (63, 's'): 11,
  (63, 't'): 11,
  (63, 'u'): 11,
  (63, 'v'): 11,
  (63, 'w'): 11,
  (63, 'x'): 11,
  (63, 'y'): 11,
  (63, 'z'): 11,
  (64, '0'): 11,
  (64, '1'): 11,
  (64, '2'): 11,
  (64, '3'): 11,
  (64, '4'): 11,
  (64, '5'): 11,
  (64, '6'): 11,
  (64, '7'): 11,
  (64, '8'): 11,
  (64, '9'): 11,
  (64, 'A'): 11,
  (64, 'B'): 11,
  (64, 'C'): 11,
  (64, 'D'): 11,
  (64, 'E'): 11,
  (64, 'F'): 11,
  (64, 'G'): 11,
  (64, 'H'): 11,
  (64, 'I'): 11,
  (64, 'J'): 11,
  (64, 'K'): 11,
  (64, 'L'): 11,
  (64, 'M'): 11,
  (64, 'N'): 11,
  (64, 'O'): 11,
  (64, 'P'): 11,
  (64, 'Q'): 11,
  (64, 'R'): 11,
  (64, 'S'): 11,
  (64, 'T'): 11,
  (64, 'U'): 11,
  (64, 'V'): 11,
  (64, 'W'): 11,
  (64, 'X'): 11,
  (64, 'Y'): 11,
  (64, 'Z'): 11,
  (64, '_'): 65,
  (64, 'a'): 11,
  (64, 'b'): 11,
  (64, 'c'): 11,
  (64, 'd'): 11,
  (64, 'e'): 11,
  (64, 'f'): 11,
  (64, 'g'): 11,
  (64, 'h'): 11,
  (64, 'i'): 11,
  (64, 'j'): 11,
  (64, 'k'): 11,
  (64, 'l'): 11,
  (64, 'm'): 11,
  (64, 'n'): 11,
  (64, 'o'): 11,
  (64, 'p'): 11,
  (64, 'q'): 11,
  (64, 'r'): 11,
  (64, 's'): 11,
  (64, 't'): 11,
  (64, 'u'): 11,
  (64, 'v'): 11,
  (64, 'w'): 11,
  (64, 'x'): 11,
  (64, 'y'): 11,
  (64, 'z'): 11,
  (65, '0'): 11,
  (65, '1'): 11,
  (65, '2'): 11,
  (65, '3'): 11,
  (65, '4'): 11,
  (65, '5'): 11,
  (65, '6'): 11,
  (65, '7'): 11,
  (65, '8'): 11,
  (65, '9'): 11,
  (65, 'A'): 11,
  (65, 'B'): 11,
  (65, 'C'): 11,
  (65, 'D'): 11,
  (65, 'E'): 11,
  (65, 'F'): 11,
  (65, 'G'): 11,
  (65, 'H'): 11,
  (65, 'I'): 11,
  (65, 'J'): 11,
  (65, 'K'): 11,
  (65, 'L'): 11,
  (65, 'M'): 11,
  (65, 'N'): 11,
  (65, 'O'): 11,
  (65, 'P'): 11,
  (65, 'Q'): 11,
  (65, 'R'): 11,
  (65, 'S'): 11,
  (65, 'T'): 11,
  (65, 'U'): 11,
  (65, 'V'): 11,
  (65, 'W'): 11,
  (65, 'X'): 11,
  (65, 'Y'): 11,
  (65, 'Z'): 11,
  (65, '_'): 11,
  (65, 'a'): 11,
  (65, 'b'): 11,
  (65, 'c'): 11,
  (65, 'd'): 11,
  (65, 'e'): 11,
  (65, 'f'): 11,
  (65, 'g'): 11,
  (65, 'h'): 11,
  (65, 'i'): 11,
  (65, 'j'): 11,
  (65, 'k'): 11,
  (65, 'l'): 11,
  (65, 'm'): 11,
  (65, 'n'): 11,
  (65, 'o'): 11,
  (65, 'p'): 66,
  (65, 'q'): 11,
  (65, 'r'): 11,
  (65, 's'): 11,
  (65, 't'): 11,
  (65, 'u'): 11,
  (65, 'v'): 11,
  (65, 'w'): 11,
  (65, 'x'): 11,
  (65, 'y'): 11,
  (65, 'z'): 11,
  (66, '0'): 11,
  (66, '1'): 11,
  (66, '2'): 11,
  (66, '3'): 11,
  (66, '4'): 11,
  (66, '5'): 11,
  (66, '6'): 11,
  (66, '7'): 11,
  (66, '8'): 11,
  (66, '9'): 11,
  (66, 'A'): 11,
  (66, 'B'): 11,
  (66, 'C'): 11,
  (66, 'D'): 11,
  (66, 'E'): 11,
  (66, 'F'): 11,
  (66, 'G'): 11,
  (66, 'H'): 11,
  (66, 'I'): 11,
  (66, 'J'): 11,
  (66, 'K'): 11,
  (66, 'L'): 11,
  (66, 'M'): 11,
  (66, 'N'): 11,
  (66, 'O'): 11,
  (66, 'P'): 11,
  (66, 'Q'): 11,
  (66, 'R'): 11,
  (66, 'S'): 11,
  (66, 'T'): 11,
  (66, 'U'): 11,
  (66, 'V'): 11,
  (66, 'W'): 11,
  (66, 'X'): 11,
  (66, 'Y'): 11,
  (66, 'Z'): 11,
  (66, '_'): 11,
  (66, 'a'): 11,
  (66, 'b'): 11,
  (66, 'c'): 11,
  (66, 'd'): 11,
  (66, 'e'): 11,
  (66, 'f'): 11,
  (66, 'g'): 11,
  (66, 'h'): 11,
  (66, 'i'): 11,
  (66, 'j'): 11,
  (66, 'k'): 11,
  (66, 'l'): 11,
  (66, 'm'): 11,
  (66, 'n'): 11,
  (66, 'o'): 11,
  (66, 'p'): 11,
  (66, 'q'): 11,
  (66, 'r'): 67,
  (66, 's'): 11,
  (66, 't'): 11,
  (66, 'u'): 11,
  (66, 'v'): 11,
  (66, 'w'): 11,
  (66, 'x'): 11,
  (66, 'y'): 11,
  (66, 'z'): 11,
  (67, '0'): 11,
  (67, '1'): 11,
  (67, '2'): 11,
  (67, '3'): 11,
  (67, '4'): 11,
  (67, '5'): 11,
  (67, '6'): 11,
  (67, '7'): 11,
  (67, '8'): 11,
  (67, '9'): 11,
  (67, 'A'): 11,
  (67, 'B'): 11,
  (67, 'C'): 11,
  (67, 'D'): 11,
  (67, 'E'): 11,
  (67, 'F'): 11,
  (67, 'G'): 11,
  (67, 'H'): 11,
  (67, 'I'): 11,
  (67, 'J'): 11,
  (67, 'K'): 11,
  (67, 'L'): 11,
  (67, 'M'): 11,
  (67, 'N'): 11,
  (67, 'O'): 11,
  (67, 'P'): 11,
  (67, 'Q'): 11,
  (67, 'R'): 11,
  (67, 'S'): 11,
  (67, 'T'): 11,
  (67, 'U'): 11,
  (67, 'V'): 11,
  (67, 'W'): 11,
  (67, 'X'): 11,
  (67, 'Y'): 11,
  (67, 'Z'): 11,
  (67, '_'): 11,
  (67, 'a'): 11,
  (67, 'b'): 11,
  (67, 'c'): 11,
  (67, 'd'): 11,
  (67, 'e'): 68,
  (67, 'f'): 11,
  (67, 'g'): 11,
  (67, 'h'): 11,
  (67, 'i'): 11,
  (67, 'j'): 11,
  (67, 'k'): 11,
  (67, 'l'): 11,
  (67, 'm'): 11,
  (67, 'n'): 11,
  (67, 'o'): 11,
  (67, 'p'): 11,
  (67, 'q'): 11,
  (67, 'r'): 11,
  (67, 's'): 11,
  (67, 't'): 11,
  (67, 'u'): 11,
  (67, 'v'): 11,
  (67, 'w'): 11,
  (67, 'x'): 11,
  (67, 'y'): 11,
  (67, 'z'): 11,
  (68, '0'): 11,
  (68, '1'): 11,
  (68, '2'): 11,
  (68, '3'): 11,
  (68, '4'): 11,
  (68, '5'): 11,
  (68, '6'): 11,
  (68, '7'): 11,
  (68, '8'): 11,
  (68, '9'): 11,
  (68, 'A'): 11,
  (68, 'B'): 11,
  (68, 'C'): 11,
  (68, 'D'): 11,
  (68, 'E'): 11,
  (68, 'F'): 11,
  (68, 'G'): 11,
  (68, 'H'): 11,
  (68, 'I'): 11,
  (68, 'J'): 11,
  (68, 'K'): 11,
  (68, 'L'): 11,
  (68, 'M'): 11,
  (68, 'N'): 11,
  (68, 'O'): 11,
  (68, 'P'): 11,
  (68, 'Q'): 11,
  (68, 'R'): 11,
  (68, 'S'): 11,
  (68, 'T'): 11,
  (68, 'U'): 11,
  (68, 'V'): 11,
  (68, 'W'): 11,
  (68, 'X'): 11,
  (68, 'Y'): 11,
  (68, 'Z'): 11,
  (68, '_'): 11,
  (68, 'a'): 11,
  (68, 'b'): 11,
  (68, 'c'): 11,
  (68, 'd'): 69,
  (68, 'e'): 11,
  (68, 'f'): 11,
  (68, 'g'): 11,
  (68, 'h'): 11,
  (68, 'i'): 11,
  (68, 'j'): 11,
  (68, 'k'): 11,
  (68, 'l'): 11,
  (68, 'm'): 11,
  (68, 'n'): 11,
  (68, 'o'): 11,
  (68, 'p'): 11,
  (68, 'q'): 11,
  (68, 'r'): 11,
  (68, 's'): 11,
  (68, 't'): 11,
  (68, 'u'): 11,
  (68, 'v'): 11,
  (68, 'w'): 11,
  (68, 'x'): 11,
  (68, 'y'): 11,
  (68, 'z'): 11,
  (69, '0'): 11,
  (69, '1'): 11,
  (69, '2'): 11,
  (69, '3'): 11,
  (69, '4'): 11,
  (69, '5'): 11,
  (69, '6'): 11,
  (69, '7'): 11,
  (69, '8'): 11,
  (69, '9'): 11,
  (69, 'A'): 11,
  (69, 'B'): 11,
  (69, 'C'): 11,
  (69, 'D'): 11,
  (69, 'E'): 11,
  (69, 'F'): 11,
  (69, 'G'): 11,
  (69, 'H'): 11,
  (69, 'I'): 11,
  (69, 'J'): 11,
  (69, 'K'): 11,
  (69, 'L'): 11,
  (69, 'M'): 11,
  (69, 'N'): 11,
  (69, 'O'): 11,
  (69, 'P'): 11,
  (69, 'Q'): 11,
  (69, 'R'): 11,
  (69, 'S'): 11,
  (69, 'T'): 11,
  (69, 'U'): 11,
  (69, 'V'): 11,
  (69, 'W'): 11,
  (69, 'X'): 11,
  (69, 'Y'): 11,
  (69, 'Z'): 11,
  (69, '_'): 11,
  (69, 'a'): 11,
  (69, 'b'): 11,
  (69, 'c'): 11,
  (69, 'd'): 11,
  (69, 'e'): 11,
  (69, 'f'): 11,
  (69, 'g'): 11,
  (69, 'h'): 11,
  (69, 'i'): 70,
  (69, 'j'): 11,
  (69, 'k'): 11,
  (69, 'l'): 11,
  (69, 'm'): 11,
  (69, 'n'): 11,
  (69, 'o'): 11,
  (69, 'p'): 11,
  (69, 'q'): 11,
  (69, 'r'): 11,
  (69, 's'): 11,
  (69, 't'): 11,
  (69, 'u'): 11,
  (69, 'v'): 11,
  (69, 'w'): 11,
  (69, 'x'): 11,
  (69, 'y'): 11,
  (69, 'z'): 11,
  (70, '0'): 11,
  (70, '1'): 11,
  (70, '2'): 11,
  (70, '3'): 11,
  (70, '4'): 11,
  (70, '5'): 11,
  (70, '6'): 11,
  (70, '7'): 11,
  (70, '8'): 11,
  (70, '9'): 11,
  (70, 'A'): 11,
  (70, 'B'): 11,
  (70, 'C'): 11,
  (70, 'D'): 11,
  (70, 'E'): 11,
  (70, 'F'): 11,
  (70, 'G'): 11,
  (70, 'H'): 11,
  (70, 'I'): 11,
  (70, 'J'): 11,
  (70, 'K'): 11,
  (70, 'L'): 11,
  (70, 'M'): 11,
  (70, 'N'): 11,
  (70, 'O'): 11,
  (70, 'P'): 11,
  (70, 'Q'): 11,
  (70, 'R'): 11,
  (70, 'S'): 11,
  (70, 'T'): 11,
  (70, 'U'): 11,
  (70, 'V'): 11,
  (70, 'W'): 11,
  (70, 'X'): 11,
  (70, 'Y'): 11,
  (70, 'Z'): 11,
  (70, '_'): 11,
  (70, 'a'): 11,
  (70, 'b'): 11,
  (70, 'c'): 71,
  (70, 'd'): 11,
  (70, 'e'): 11,
  (70, 'f'): 11,
  (70, 'g'): 11,
  (70, 'h'): 11,
  (70, 'i'): 11,
  (70, 'j'): 11,
  (70, 'k'): 11,
  (70, 'l'): 11,
  (70, 'm'): 11,
  (70, 'n'): 11,
  (70, 'o'): 11,
  (70, 'p'): 11,
  (70, 'q'): 11,
  (70, 'r'): 11,
  (70, 's'): 11,
  (70, 't'): 11,
  (70, 'u'): 11,
  (70, 'v'): 11,
  (70, 'w'): 11,
  (70, 'x'): 11,
  (70, 'y'): 11,
  (70, 'z'): 11,
  (71, '0'): 11,
  (71, '1'): 11,
  (71, '2'): 11,
  (71, '3'): 11,
  (71, '4'): 11,
  (71, '5'): 11,
  (71, '6'): 11,
  (71, '7'): 11,
  (71, '8'): 11,
  (71, '9'): 11,
  (71, 'A'): 11,
  (71, 'B'): 11,
  (71, 'C'): 11,
  (71, 'D'): 11,
  (71, 'E'): 11,
  (71, 'F'): 11,
  (71, 'G'): 11,
  (71, 'H'): 11,
  (71, 'I'): 11,
  (71, 'J'): 11,
  (71, 'K'): 11,
  (71, 'L'): 11,
  (71, 'M'): 11,
  (71, 'N'): 11,
  (71, 'O'): 11,
  (71, 'P'): 11,
  (71, 'Q'): 11,
  (71, 'R'): 11,
  (71, 'S'): 11,
  (71, 'T'): 11,
  (71, 'U'): 11,
  (71, 'V'): 11,
  (71, 'W'): 11,
  (71, 'X'): 11,
  (71, 'Y'): 11,
  (71, 'Z'): 11,
  (71, '_'): 11,
  (71, 'a'): 72,
  (71, 'b'): 11,
  (71, 'c'): 11,
  (71, 'd'): 11,
  (71, 'e'): 11,
  (71, 'f'): 11,
  (71, 'g'): 11,
  (71, 'h'): 11,
  (71, 'i'): 11,
  (71, 'j'): 11,
  (71, 'k'): 11,
  (71, 'l'): 11,
  (71, 'm'): 11,
  (71, 'n'): 11,
  (71, 'o'): 11,
  (71, 'p'): 11,
  (71, 'q'): 11,
  (71, 'r'): 11,
  (71, 's'): 11,
  (71, 't'): 11,
  (71, 'u'): 11,
  (71, 'v'): 11,
  (71, 'w'): 11,
  (71, 'x'): 11,
  (71, 'y'): 11,
  (71, 'z'): 11,
  (72, '0'): 11,
  (72, '1'): 11,
  (72, '2'): 11,
  (72, '3'): 11,
  (72, '4'): 11,
  (72, '5'): 11,
  (72, '6'): 11,
  (72, '7'): 11,
  (72, '8'): 11,
  (72, '9'): 11,
  (72, 'A'): 11,
  (72, 'B'): 11,
  (72, 'C'): 11,
  (72, 'D'): 11,
  (72, 'E'): 11,
  (72, 'F'): 11,
  (72, 'G'): 11,
  (72, 'H'): 11,
  (72, 'I'): 11,
  (72, 'J'): 11,
  (72, 'K'): 11,
  (72, 'L'): 11,
  (72, 'M'): 11,
  (72, 'N'): 11,
  (72, 'O'): 11,
  (72, 'P'): 11,
  (72, 'Q'): 11,
  (72, 'R'): 11,
  (72, 'S'): 11,
  (72, 'T'): 11,
  (72, 'U'): 11,
  (72, 'V'): 11,
  (72, 'W'): 11,
  (72, 'X'): 11,
  (72, 'Y'): 11,
  (72, 'Z'): 11,
  (72, '_'): 11,
  (72, 'a'): 11,
  (72, 'b'): 11,
  (72, 'c'): 11,
  (72, 'd'): 11,
  (72, 'e'): 11,
  (72, 'f'): 11,
  (72, 'g'): 11,
  (72, 'h'): 11,
  (72, 'i'): 11,
  (72, 'j'): 11,
  (72, 'k'): 11,
  (72, 'l'): 11,
  (72, 'm'): 11,
  (72, 'n'): 11,
  (72, 'o'): 11,
  (72, 'p'): 11,
  (72, 'q'): 11,
  (72, 'r'): 11,
  (72, 's'): 11,
  (72, 't'): 73,
  (72, 'u'): 11,
  (72, 'v'): 11,
  (72, 'w'): 11,
  (72, 'x'): 11,
  (72, 'y'): 11,
  (72, 'z'): 11,
  (73, '0'): 11,
  (73, '1'): 11,
  (73, '2'): 11,
  (73, '3'): 11,
  (73, '4'): 11,
  (73, '5'): 11,
  (73, '6'): 11,
  (73, '7'): 11,
  (73, '8'): 11,
  (73, '9'): 11,
  (73, 'A'): 11,
  (73, 'B'): 11,
  (73, 'C'): 11,
  (73, 'D'): 11,
  (73, 'E'): 11,
  (73, 'F'): 11,
  (73, 'G'): 11,
  (73, 'H'): 11,
  (73, 'I'): 11,
  (73, 'J'): 11,
  (73, 'K'): 11,
  (73, 'L'): 11,
  (73, 'M'): 11,
  (73, 'N'): 11,
  (73, 'O'): 11,
  (73, 'P'): 11,
  (73, 'Q'): 11,
  (73, 'R'): 11,
  (73, 'S'): 11,
  (73, 'T'): 11,
  (73, 'U'): 11,
  (73, 'V'): 11,
  (73, 'W'): 11,
  (73, 'X'): 11,
  (73, 'Y'): 11,
  (73, 'Z'): 11,
  (73, '_'): 11,
  (73, 'a'): 11,
  (73, 'b'): 11,
  (73, 'c'): 11,
  (73, 'd'): 11,
  (73, 'e'): 74,
  (73, 'f'): 11,
  (73, 'g'): 11,
  (73, 'h'): 11,
  (73, 'i'): 11,
  (73, 'j'): 11,
  (73, 'k'): 11,
  (73, 'l'): 11,
  (73, 'm'): 11,
  (73, 'n'): 11,
  (73, 'o'): 11,
  (73, 'p'): 11,
  (73, 'q'): 11,
  (73, 'r'): 11,
  (73, 's'): 11,
  (73, 't'): 11,
  (73, 'u'): 11,
  (73, 'v'): 11,
  (73, 'w'): 11,
  (73, 'x'): 11,
  (73, 'y'): 11,
  (73, 'z'): 11,
  (74, '0'): 11,
  (74, '1'): 11,
  (74, '2'): 11,
  (74, '3'): 11,
  (74, '4'): 11,
  (74, '5'): 11,
  (74, '6'): 11,
  (74, '7'): 11,
  (74, '8'): 11,
  (74, '9'): 11,
  (74, 'A'): 11,
  (74, 'B'): 11,
  (74, 'C'): 11,
  (74, 'D'): 11,
  (74, 'E'): 11,
  (74, 'F'): 11,
  (74, 'G'): 11,
  (74, 'H'): 11,
  (74, 'I'): 11,
  (74, 'J'): 11,
  (74, 'K'): 11,
  (74, 'L'): 11,
  (74, 'M'): 11,
  (74, 'N'): 11,
  (74, 'O'): 11,
  (74, 'P'): 11,
  (74, 'Q'): 11,
  (74, 'R'): 11,
  (74, 'S'): 11,
  (74, 'T'): 11,
  (74, 'U'): 11,
  (74, 'V'): 11,
  (74, 'W'): 11,
  (74, 'X'): 11,
  (74, 'Y'): 11,
  (74, 'Z'): 11,
  (74, '_'): 11,
  (74, 'a'): 11,
  (74, 'b'): 11,
  (74, 'c'): 11,
  (74, 'd'): 11,
  (74, 'e'): 11,
  (74, 'f'): 11,
  (74, 'g'): 11,
  (74, 'h'): 11,
  (74, 'i'): 11,
  (74, 'j'): 11,
  (74, 'k'): 11,
  (74, 'l'): 11,
  (74, 'm'): 11,
  (74, 'n'): 11,
  (74, 'o'): 11,
  (74, 'p'): 11,
  (74, 'q'): 11,
  (74, 'r'): 11,
  (74, 's'): 11,
  (74, 't'): 11,
  (74, 'u'): 11,
  (74, 'v'): 11,
  (74, 'w'): 11,
  (74, 'x'): 11,
  (74, 'y'): 11,
  (74, 'z'): 11,
  (75, '0'): 11,
  (75, '1'): 11,
  (75, '2'): 11,
  (75, '3'): 11,
  (75, '4'): 11,
  (75, '5'): 11,
  (75, '6'): 11,
  (75, '7'): 11,
  (75, '8'): 11,
  (75, '9'): 11,
  (75, 'A'): 11,
  (75, 'B'): 11,
  (75, 'C'): 11,
  (75, 'D'): 11,
  (75, 'E'): 11,
  (75, 'F'): 11,
  (75, 'G'): 11,
  (75, 'H'): 11,
  (75, 'I'): 11,
  (75, 'J'): 11,
  (75, 'K'): 11,
  (75, 'L'): 11,
  (75, 'M'): 11,
  (75, 'N'): 11,
  (75, 'O'): 11,
  (75, 'P'): 11,
  (75, 'Q'): 11,
  (75, 'R'): 11,
  (75, 'S'): 11,
  (75, 'T'): 11,
  (75, 'U'): 11,
  (75, 'V'): 11,
  (75, 'W'): 11,
  (75, 'X'): 11,
  (75, 'Y'): 11,
  (75, 'Z'): 11,
  (75, '_'): 11,
  (75, 'a'): 11,
  (75, 'b'): 11,
  (75, 'c'): 11,
  (75, 'd'): 11,
  (75, 'e'): 11,
  (75, 'f'): 11,
  (75, 'g'): 11,
  (75, 'h'): 11,
  (75, 'i'): 77,
  (75, 'j'): 11,
  (75, 'k'): 11,
  (75, 'l'): 11,
  (75, 'm'): 11,
  (75, 'n'): 11,
  (75, 'o'): 11,
  (75, 'p'): 11,
  (75, 'q'): 11,
  (75, 'r'): 11,
  (75, 's'): 11,
  (75, 't'): 11,
  (75, 'u'): 11,
  (75, 'v'): 11,
  (75, 'w'): 11,
  (75, 'x'): 11,
  (75, 'y'): 11,
  (75, 'z'): 11,
  (76, '0'): 11,
  (76, '1'): 11,
  (76, '2'): 11,
  (76, '3'): 11,
  (76, '4'): 11,
  (76, '5'): 11,
  (76, '6'): 11,
  (76, '7'): 11,
  (76, '8'): 11,
  (76, '9'): 11,
  (76, 'A'): 11,
  (76, 'B'): 11,
  (76, 'C'): 11,
  (76, 'D'): 11,
  (76, 'E'): 11,
  (76, 'F'): 11,
  (76, 'G'): 11,
  (76, 'H'): 11,
  (76, 'I'): 11,
  (76, 'J'): 11,
  (76, 'K'): 11,
  (76, 'L'): 11,
  (76, 'M'): 11,
  (76, 'N'): 11,
  (76, 'O'): 11,
  (76, 'P'): 11,
  (76, 'Q'): 11,
  (76, 'R'): 11,
  (76, 'S'): 11,
  (76, 'T'): 11,
  (76, 'U'): 11,
  (76, 'V'): 11,
  (76, 'W'): 11,
  (76, 'X'): 11,
  (76, 'Y'): 11,
  (76, 'Z'): 11,
  (76, '_'): 11,
  (76, 'a'): 11,
  (76, 'b'): 11,
  (76, 'c'): 11,
  (76, 'd'): 11,
  (76, 'e'): 11,
  (76, 'f'): 11,
  (76, 'g'): 11,
  (76, 'h'): 11,
  (76, 'i'): 11,
  (76, 'j'): 11,
  (76, 'k'): 11,
  (76, 'l'): 11,
  (76, 'm'): 11,
  (76, 'n'): 11,
  (76, 'o'): 11,
  (76, 'p'): 11,
  (76, 'q'): 11,
  (76, 'r'): 11,
  (76, 's'): 11,
  (76, 't'): 11,
  (76, 'u'): 11,
  (76, 'v'): 11,
  (76, 'w'): 11,
  (76, 'x'): 11,
  (76, 'y'): 11,
  (76, 'z'): 11,
  (77, '0'): 11,
  (77, '1'): 11,
  (77, '2'): 11,
  (77, '3'): 11,
  (77, '4'): 11,
  (77, '5'): 11,
  (77, '6'): 11,
  (77, '7'): 11,
  (77, '8'): 11,
  (77, '9'): 11,
  (77, 'A'): 11,
  (77, 'B'): 11,
  (77, 'C'): 11,
  (77, 'D'): 11,
  (77, 'E'): 11,
  (77, 'F'): 11,
  (77, 'G'): 11,
  (77, 'H'): 11,
  (77, 'I'): 11,
  (77, 'J'): 11,
  (77, 'K'): 11,
  (77, 'L'): 11,
  (77, 'M'): 11,
  (77, 'N'): 11,
  (77, 'O'): 11,
  (77, 'P'): 11,
  (77, 'Q'): 11,
  (77, 'R'): 11,
  (77, 'S'): 11,
  (77, 'T'): 11,
  (77, 'U'): 11,
  (77, 'V'): 11,
  (77, 'W'): 11,
  (77, 'X'): 11,
  (77, 'Y'): 11,
  (77, 'Z'): 11,
  (77, '_'): 11,
  (77, 'a'): 11,
  (77, 'b'): 11,
  (77, 'c'): 11,
  (77, 'd'): 11,
  (77, 'e'): 11,
  (77, 'f'): 11,
  (77, 'g'): 11,
  (77, 'h'): 11,
  (77, 'i'): 11,
  (77, 'j'): 11,
  (77, 'k'): 11,
  (77, 'l'): 11,
  (77, 'm'): 11,
  (77, 'n'): 11,
  (77, 'o'): 11,
  (77, 'p'): 11,
  (77, 'q'): 11,
  (77, 'r'): 11,
  (77, 's'): 11,
  (77, 't'): 78,
  (77, 'u'): 11,
  (77, 'v'): 11,
  (77, 'w'): 11,
  (77, 'x'): 11,
  (77, 'y'): 11,
  (77, 'z'): 11,
  (78, '0'): 11,
  (78, '1'): 11,
  (78, '2'): 11,
  (78, '3'): 11,
  (78, '4'): 11,
  (78, '5'): 11,
  (78, '6'): 11,
  (78, '7'): 11,
  (78, '8'): 11,
  (78, '9'): 11,
  (78, 'A'): 11,
  (78, 'B'): 11,
  (78, 'C'): 11,
  (78, 'D'): 11,
  (78, 'E'): 11,
  (78, 'F'): 11,
  (78, 'G'): 11,
  (78, 'H'): 11,
  (78, 'I'): 11,
  (78, 'J'): 11,
  (78, 'K'): 11,
  (78, 'L'): 11,
  (78, 'M'): 11,
  (78, 'N'): 11,
  (78, 'O'): 11,
  (78, 'P'): 11,
  (78, 'Q'): 11,
  (78, 'R'): 11,
  (78, 'S'): 11,
  (78, 'T'): 11,
  (78, 'U'): 11,
  (78, 'V'): 11,
  (78, 'W'): 11,
  (78, 'X'): 11,
  (78, 'Y'): 11,
  (78, 'Z'): 11,
  (78, '_'): 11,
  (78, 'a'): 11,
  (78, 'b'): 11,
  (78, 'c'): 11,
  (78, 'd'): 11,
  (78, 'e'): 11,
  (78, 'f'): 11,
  (78, 'g'): 11,
  (78, 'h'): 11,
  (78, 'i'): 79,
  (78, 'j'): 11,
  (78, 'k'): 11,
  (78, 'l'): 11,
  (78, 'm'): 11,
  (78, 'n'): 11,
  (78, 'o'): 11,
  (78, 'p'): 11,
  (78, 'q'): 11,
  (78, 'r'): 11,
  (78, 's'): 11,
  (78, 't'): 11,
  (78, 'u'): 11,
  (78, 'v'): 11,
  (78, 'w'): 11,
  (78, 'x'): 11,
  (78, 'y'): 11,
  (78, 'z'): 11,
  (79, '0'): 11,
  (79, '1'): 11,
  (79, '2'): 11,
  (79, '3'): 11,
  (79, '4'): 11,
  (79, '5'): 11,
  (79, '6'): 11,
  (79, '7'): 11,
  (79, '8'): 11,
  (79, '9'): 11,
  (79, 'A'): 11,
  (79, 'B'): 11,
  (79, 'C'): 11,
  (79, 'D'): 11,
  (79, 'E'): 11,
  (79, 'F'): 11,
  (79, 'G'): 11,
  (79, 'H'): 11,
  (79, 'I'): 11,
  (79, 'J'): 11,
  (79, 'K'): 11,
  (79, 'L'): 11,
  (79, 'M'): 11,
  (79, 'N'): 11,
  (79, 'O'): 11,
  (79, 'P'): 11,
  (79, 'Q'): 11,
  (79, 'R'): 11,
  (79, 'S'): 11,
  (79, 'T'): 11,
  (79, 'U'): 11,
  (79, 'V'): 11,
  (79, 'W'): 11,
  (79, 'X'): 11,
  (79, 'Y'): 11,
  (79, 'Z'): 11,
  (79, '_'): 11,
  (79, 'a'): 80,
  (79, 'b'): 11,
  (79, 'c'): 11,
  (79, 'd'): 11,
  (79, 'e'): 11,
  (79, 'f'): 11,
  (79, 'g'): 11,
  (79, 'h'): 11,
  (79, 'i'): 11,
  (79, 'j'): 11,
  (79, 'k'): 11,
  (79, 'l'): 11,
  (79, 'm'): 11,
  (79, 'n'): 11,
  (79, 'o'): 11,
  (79, 'p'): 11,
  (79, 'q'): 11,
  (79, 'r'): 11,
  (79, 's'): 11,
  (79, 't'): 11,
  (79, 'u'): 11,
  (79, 'v'): 11,
  (79, 'w'): 11,
  (79, 'x'): 11,
  (79, 'y'): 11,
  (79, 'z'): 11,
  (80, '0'): 11,
  (80, '1'): 11,
  (80, '2'): 11,
  (80, '3'): 11,
  (80, '4'): 11,
  (80, '5'): 11,
  (80, '6'): 11,
  (80, '7'): 11,
  (80, '8'): 11,
  (80, '9'): 11,
  (80, 'A'): 11,
  (80, 'B'): 11,
  (80, 'C'): 11,
  (80, 'D'): 11,
  (80, 'E'): 11,
  (80, 'F'): 11,
  (80, 'G'): 11,
  (80, 'H'): 11,
  (80, 'I'): 11,
  (80, 'J'): 11,
  (80, 'K'): 11,
  (80, 'L'): 11,
  (80, 'M'): 11,
  (80, 'N'): 11,
  (80, 'O'): 11,
  (80, 'P'): 11,
  (80, 'Q'): 11,
  (80, 'R'): 11,
  (80, 'S'): 11,
  (80, 'T'): 11,
  (80, 'U'): 11,
  (80, 'V'): 11,
  (80, 'W'): 11,
  (80, 'X'): 11,
  (80, 'Y'): 11,
  (80, 'Z'): 11,
  (80, '_'): 11,
  (80, 'a'): 11,
  (80, 'b'): 11,
  (80, 'c'): 11,
  (80, 'd'): 11,
  (80, 'e'): 11,
  (80, 'f'): 11,
  (80, 'g'): 11,
  (80, 'h'): 11,
  (80, 'i'): 11,
  (80, 'j'): 11,
  (80, 'k'): 11,
  (80, 'l'): 81,
  (80, 'm'): 11,
  (80, 'n'): 11,
  (80, 'o'): 11,
  (80, 'p'): 11,
  (80, 'q'): 11,
  (80, 'r'): 11,
  (80, 's'): 11,
  (80, 't'): 11,
  (80, 'u'): 11,
  (80, 'v'): 11,
  (80, 'w'): 11,
  (80, 'x'): 11,
  (80, 'y'): 11,
  (80, 'z'): 11,
  (81, '0'): 11,
  (81, '1'): 11,
  (81, '2'): 11,
  (81, '3'): 11,
  (81, '4'): 11,
  (81, '5'): 11,
  (81, '6'): 11,
  (81, '7'): 11,
  (81, '8'): 11,
  (81, '9'): 11,
  (81, 'A'): 11,
  (81, 'B'): 11,
  (81, 'C'): 11,
  (81, 'D'): 11,
  (81, 'E'): 11,
  (81, 'F'): 11,
  (81, 'G'): 11,
  (81, 'H'): 11,
  (81, 'I'): 11,
  (81, 'J'): 11,
  (81, 'K'): 11,
  (81, 'L'): 11,
  (81, 'M'): 11,
  (81, 'N'): 11,
  (81, 'O'): 11,
  (81, 'P'): 11,
  (81, 'Q'): 11,
  (81, 'R'): 11,
  (81, 'S'): 11,
  (81, 'T'): 11,
  (81, 'U'): 11,
  (81, 'V'): 11,
  (81, 'W'): 11,
  (81, 'X'): 11,
  (81, 'Y'): 11,
  (81, 'Z'): 11,
  (81, '_'): 11,
  (81, 'a'): 11,
  (81, 'b'): 11,
  (81, 'c'): 11,
  (81, 'd'): 11,
  (81, 'e'): 11,
  (81, 'f'): 11,
  (81, 'g'): 11,
  (81, 'h'): 11,
  (81, 'i'): 82,
  (81, 'j'): 11,
  (81, 'k'): 11,
  (81, 'l'): 11,
  (81, 'm'): 11,
  (81, 'n'): 11,
  (81, 'o'): 11,
  (81, 'p'): 11,
  (81, 'q'): 11,
  (81, 'r'): 11,
  (81, 's'): 11,
  (81, 't'): 11,
  (81, 'u'): 11,
  (81, 'v'): 11,
  (81, 'w'): 11,
  (81, 'x'): 11,
  (81, 'y'): 11,
  (81, 'z'): 11,
  (82, '0'): 11,
  (82, '1'): 11,
  (82, '2'): 11,
  (82, '3'): 11,
  (82, '4'): 11,
  (82, '5'): 11,
  (82, '6'): 11,
  (82, '7'): 11,
  (82, '8'): 11,
  (82, '9'): 11,
  (82, 'A'): 11,
  (82, 'B'): 11,
  (82, 'C'): 11,
  (82, 'D'): 11,
  (82, 'E'): 11,
  (82, 'F'): 11,
  (82, 'G'): 11,
  (82, 'H'): 11,
  (82, 'I'): 11,
  (82, 'J'): 11,
  (82, 'K'): 11,
  (82, 'L'): 11,
  (82, 'M'): 11,
  (82, 'N'): 11,
  (82, 'O'): 11,
  (82, 'P'): 11,
  (82, 'Q'): 11,
  (82, 'R'): 11,
  (82, 'S'): 11,
  (82, 'T'): 11,
  (82, 'U'): 11,
  (82, 'V'): 11,
  (82, 'W'): 11,
  (82, 'X'): 11,
  (82, 'Y'): 11,
  (82, 'Z'): 11,
  (82, '_'): 11,
  (82, 'a'): 11,
  (82, 'b'): 11,
  (82, 'c'): 11,
  (82, 'd'): 11,
  (82, 'e'): 11,
  (82, 'f'): 11,
  (82, 'g'): 11,
  (82, 'h'): 11,
  (82, 'i'): 11,
  (82, 'j'): 11,
  (82, 'k'): 11,
  (82, 'l'): 11,
  (82, 'm'): 11,
  (82, 'n'): 11,
  (82, 'o'): 11,
  (82, 'p'): 11,
  (82, 'q'): 11,
  (82, 'r'): 11,
  (82, 's'): 11,
  (82, 't'): 11,
  (82, 'u'): 11,
  (82, 'v'): 11,
  (82, 'w'): 11,
  (82, 'x'): 11,
  (82, 'y'): 11,
  (82, 'z'): 83,
  (83, '0'): 11,
  (83, '1'): 11,
  (83, '2'): 11,
  (83, '3'): 11,
  (83, '4'): 11,
  (83, '5'): 11,
  (83, '6'): 11,
  (83, '7'): 11,
  (83, '8'): 11,
  (83, '9'): 11,
  (83, 'A'): 11,
  (83, 'B'): 11,
  (83, 'C'): 11,
  (83, 'D'): 11,
  (83, 'E'): 11,
  (83, 'F'): 11,
  (83, 'G'): 11,
  (83, 'H'): 11,
  (83, 'I'): 11,
  (83, 'J'): 11,
  (83, 'K'): 11,
  (83, 'L'): 11,
  (83, 'M'): 11,
  (83, 'N'): 11,
  (83, 'O'): 11,
  (83, 'P'): 11,
  (83, 'Q'): 11,
  (83, 'R'): 11,
  (83, 'S'): 11,
  (83, 'T'): 11,
  (83, 'U'): 11,
  (83, 'V'): 11,
  (83, 'W'): 11,
  (83, 'X'): 11,
  (83, 'Y'): 11,
  (83, 'Z'): 11,
  (83, '_'): 11,
  (83, 'a'): 84,
  (83, 'b'): 11,
  (83, 'c'): 11,
  (83, 'd'): 11,
  (83, 'e'): 11,
  (83, 'f'): 11,
  (83, 'g'): 11,
  (83, 'h'): 11,
  (83, 'i'): 11,
  (83, 'j'): 11,
  (83, 'k'): 11,
  (83, 'l'): 11,
  (83, 'm'): 11,
  (83, 'n'): 11,
  (83, 'o'): 11,
  (83, 'p'): 11,
  (83, 'q'): 11,
  (83, 'r'): 11,
  (83, 's'): 11,
  (83, 't'): 11,
  (83, 'u'): 11,
  (83, 'v'): 11,
  (83, 'w'): 11,
  (83, 'x'): 11,
  (83, 'y'): 11,
  (83, 'z'): 11,
  (84, '0'): 11,
  (84, '1'): 11,
  (84, '2'): 11,
  (84, '3'): 11,
  (84, '4'): 11,
  (84, '5'): 11,
  (84, '6'): 11,
  (84, '7'): 11,
  (84, '8'): 11,
  (84, '9'): 11,
  (84, 'A'): 11,
  (84, 'B'): 11,
  (84, 'C'): 11,
  (84, 'D'): 11,
  (84, 'E'): 11,
  (84, 'F'): 11,
  (84, 'G'): 11,
  (84, 'H'): 11,
  (84, 'I'): 11,
  (84, 'J'): 11,
  (84, 'K'): 11,
  (84, 'L'): 11,
  (84, 'M'): 11,
  (84, 'N'): 11,
  (84, 'O'): 11,
  (84, 'P'): 11,
  (84, 'Q'): 11,
  (84, 'R'): 11,
  (84, 'S'): 11,
  (84, 'T'): 11,
  (84, 'U'): 11,
  (84, 'V'): 11,
  (84, 'W'): 11,
  (84, 'X'): 11,
  (84, 'Y'): 11,
  (84, 'Z'): 11,
  (84, '_'): 11,
  (84, 'a'): 11,
  (84, 'b'): 11,
  (84, 'c'): 11,
  (84, 'd'): 11,
  (84, 'e'): 11,
  (84, 'f'): 11,
  (84, 'g'): 11,
  (84, 'h'): 11,
  (84, 'i'): 11,
  (84, 'j'): 11,
  (84, 'k'): 11,
  (84, 'l'): 11,
  (84, 'm'): 11,
  (84, 'n'): 11,
  (84, 'o'): 11,
  (84, 'p'): 11,
  (84, 'q'): 11,
  (84, 'r'): 11,
  (84, 's'): 11,
  (84, 't'): 85,
  (84, 'u'): 11,
  (84, 'v'): 11,
  (84, 'w'): 11,
  (84, 'x'): 11,
  (84, 'y'): 11,
  (84, 'z'): 11,
  (85, '0'): 11,
  (85, '1'): 11,
  (85, '2'): 11,
  (85, '3'): 11,
  (85, '4'): 11,
  (85, '5'): 11,
  (85, '6'): 11,
  (85, '7'): 11,
  (85, '8'): 11,
  (85, '9'): 11,
  (85, 'A'): 11,
  (85, 'B'): 11,
  (85, 'C'): 11,
  (85, 'D'): 11,
  (85, 'E'): 11,
  (85, 'F'): 11,
  (85, 'G'): 11,
  (85, 'H'): 11,
  (85, 'I'): 11,
  (85, 'J'): 11,
  (85, 'K'): 11,
  (85, 'L'): 11,
  (85, 'M'): 11,
  (85, 'N'): 11,
  (85, 'O'): 11,
  (85, 'P'): 11,
  (85, 'Q'): 11,
  (85, 'R'): 11,
  (85, 'S'): 11,
  (85, 'T'): 11,
  (85, 'U'): 11,
  (85, 'V'): 11,
  (85, 'W'): 11,
  (85, 'X'): 11,
  (85, 'Y'): 11,
  (85, 'Z'): 11,
  (85, '_'): 11,
  (85, 'a'): 11,
  (85, 'b'): 11,
  (85, 'c'): 11,
  (85, 'd'): 11,
  (85, 'e'): 11,
  (85, 'f'): 11,
  (85, 'g'): 11,
  (85, 'h'): 11,
  (85, 'i'): 86,
  (85, 'j'): 11,
  (85, 'k'): 11,
  (85, 'l'): 11,
  (85, 'm'): 11,
  (85, 'n'): 11,
  (85, 'o'): 11,
  (85, 'p'): 11,
  (85, 'q'): 11,
  (85, 'r'): 11,
  (85, 's'): 11,
  (85, 't'): 11,
  (85, 'u'): 11,
  (85, 'v'): 11,
  (85, 'w'): 11,
  (85, 'x'): 11,
  (85, 'y'): 11,
  (85, 'z'): 11,
  (86, '0'): 11,
  (86, '1'): 11,
  (86, '2'): 11,
  (86, '3'): 11,
  (86, '4'): 11,
  (86, '5'): 11,
  (86, '6'): 11,
  (86, '7'): 11,
  (86, '8'): 11,
  (86, '9'): 11,
  (86, 'A'): 11,
  (86, 'B'): 11,
  (86, 'C'): 11,
  (86, 'D'): 11,
  (86, 'E'): 11,
  (86, 'F'): 11,
  (86, 'G'): 11,
  (86, 'H'): 11,
  (86, 'I'): 11,
  (86, 'J'): 11,
  (86, 'K'): 11,
  (86, 'L'): 11,
  (86, 'M'): 11,
  (86, 'N'): 11,
  (86, 'O'): 11,
  (86, 'P'): 11,
  (86, 'Q'): 11,
  (86, 'R'): 11,
  (86, 'S'): 11,
  (86, 'T'): 11,
  (86, 'U'): 11,
  (86, 'V'): 11,
  (86, 'W'): 11,
  (86, 'X'): 11,
  (86, 'Y'): 11,
  (86, 'Z'): 11,
  (86, '_'): 11,
  (86, 'a'): 11,
  (86, 'b'): 11,
  (86, 'c'): 11,
  (86, 'd'): 11,
  (86, 'e'): 11,
  (86, 'f'): 11,
  (86, 'g'): 11,
  (86, 'h'): 11,
  (86, 'i'): 11,
  (86, 'j'): 11,
  (86, 'k'): 11,
  (86, 'l'): 11,
  (86, 'm'): 11,
  (86, 'n'): 11,
  (86, 'o'): 87,
  (86, 'p'): 11,
  (86, 'q'): 11,
  (86, 'r'): 11,
  (86, 's'): 11,
  (86, 't'): 11,
  (86, 'u'): 11,
  (86, 'v'): 11,
  (86, 'w'): 11,
  (86, 'x'): 11,
  (86, 'y'): 11,
  (86, 'z'): 11,
  (87, '0'): 11,
  (87, '1'): 11,
  (87, '2'): 11,
  (87, '3'): 11,
  (87, '4'): 11,
  (87, '5'): 11,
  (87, '6'): 11,
  (87, '7'): 11,
  (87, '8'): 11,
  (87, '9'): 11,
  (87, 'A'): 11,
  (87, 'B'): 11,
  (87, 'C'): 11,
  (87, 'D'): 11,
  (87, 'E'): 11,
  (87, 'F'): 11,
  (87, 'G'): 11,
  (87, 'H'): 11,
  (87, 'I'): 11,
  (87, 'J'): 11,
  (87, 'K'): 11,
  (87, 'L'): 11,
  (87, 'M'): 11,
  (87, 'N'): 11,
  (87, 'O'): 11,
  (87, 'P'): 11,
  (87, 'Q'): 11,
  (87, 'R'): 11,
  (87, 'S'): 11,
  (87, 'T'): 11,
  (87, 'U'): 11,
  (87, 'V'): 11,
  (87, 'W'): 11,
  (87, 'X'): 11,
  (87, 'Y'): 11,
  (87, 'Z'): 11,
  (87, '_'): 11,
  (87, 'a'): 11,
  (87, 'b'): 11,
  (87, 'c'): 11,
  (87, 'd'): 11,
  (87, 'e'): 11,
  (87, 'f'): 11,
  (87, 'g'): 11,
  (87, 'h'): 11,
  (87, 'i'): 11,
  (87, 'j'): 11,
  (87, 'k'): 11,
  (87, 'l'): 11,
  (87, 'm'): 11,
  (87, 'n'): 88,
  (87, 'o'): 11,
  (87, 'p'): 11,
  (87, 'q'): 11,
  (87, 'r'): 11,
  (87, 's'): 11,
  (87, 't'): 11,
  (87, 'u'): 11,
  (87, 'v'): 11,
  (87, 'w'): 11,
  (87, 'x'): 11,
  (87, 'y'): 11,
  (87, 'z'): 11,
  (88, '0'): 11,
  (88, '1'): 11,
  (88, '2'): 11,
  (88, '3'): 11,
  (88, '4'): 11,
  (88, '5'): 11,
  (88, '6'): 11,
  (88, '7'): 11,
  (88, '8'): 11,
  (88, '9'): 11,
  (88, 'A'): 11,
  (88, 'B'): 11,
  (88, 'C'): 11,
  (88, 'D'): 11,
  (88, 'E'): 11,
  (88, 'F'): 11,
  (88, 'G'): 11,
  (88, 'H'): 11,
  (88, 'I'): 11,
  (88, 'J'): 11,
  (88, 'K'): 11,
  (88, 'L'): 11,
  (88, 'M'): 11,
  (88, 'N'): 11,
  (88, 'O'): 11,
  (88, 'P'): 11,
  (88, 'Q'): 11,
  (88, 'R'): 11,
  (88, 'S'): 11,
  (88, 'T'): 11,
  (88, 'U'): 11,
  (88, 'V'): 11,
  (88, 'W'): 11,
  (88, 'X'): 11,
  (88, 'Y'): 11,
  (88, 'Z'): 11,
  (88, '_'): 11,
  (88, 'a'): 11,
  (88, 'b'): 11,
  (88, 'c'): 11,
  (88, 'd'): 11,
  (88, 'e'): 11,
  (88, 'f'): 11,
  (88, 'g'): 11,
  (88, 'h'): 11,
  (88, 'i'): 11,
  (88, 'j'): 11,
  (88, 'k'): 11,
  (88, 'l'): 11,
  (88, 'm'): 11,
  (88, 'n'): 11,
  (88, 'o'): 11,
  (88, 'p'): 11,
  (88, 'q'): 11,
  (88, 'r'): 11,
  (88, 's'): 11,
  (88, 't'): 11,
  (88, 'u'): 11,
  (88, 'v'): 11,
  (88, 'w'): 11,
  (88, 'x'): 11,
  (88, 'y'): 11,
  (88, 'z'): 11,
  (89, '='): 98,
  (91, '.'): 97,
  (92, '='): 96,
  (94, '='): 95,
  (99, '>'): 101,
  (102, '0'): 11,
  (102, '1'): 11,
  (102, '2'): 11,
  (102, '3'): 11,
  (102, '4'): 11,
  (102, '5'): 11,
  (102, '6'): 11,
  (102, '7'): 11,
  (102, '8'): 11,
  (102, '9'): 11,
  (102, 'A'): 11,
  (102, 'B'): 11,
  (102, 'C'): 11,
  (102, 'D'): 11,
  (102, 'E'): 11,
  (102, 'F'): 11,
  (102, 'G'): 11,
  (102, 'H'): 11,
  (102, 'I'): 11,
  (102, 'J'): 11,
  (102, 'K'): 11,
  (102, 'L'): 11,
  (102, 'M'): 11,
  (102, 'N'): 11,
  (102, 'O'): 11,
  (102, 'P'): 11,
  (102, 'Q'): 11,
  (102, 'R'): 11,
  (102, 'S'): 11,
  (102, 'T'): 11,
  (102, 'U'): 11,
  (102, 'V'): 11,
  (102, 'W'): 11,
  (102, 'X'): 11,
  (102, 'Y'): 11,
  (102, 'Z'): 11,
  (102, '_'): 11,
  (102, 'a'): 11,
  (102, 'b'): 11,
  (102, 'c'): 11,
  (102, 'd'): 11,
  (102, 'e'): 11,
  (102, 'f'): 11,
  (102, 'g'): 11,
  (102, 'h'): 11,
  (102, 'i'): 11,
  (102, 'j'): 11,
  (102, 'k'): 11,
  (102, 'l'): 11,
  (102, 'm'): 103,
  (102, 'n'): 11,
  (102, 'o'): 11,
  (102, 'p'): 11,
  (102, 'q'): 11,
  (102, 'r'): 11,
  (102, 's'): 11,
  (102, 't'): 11,
  (102, 'u'): 11,
  (102, 'v'): 11,
  (102, 'w'): 11,
  (102, 'x'): 11,
  (102, 'y'): 11,
  (102, 'z'): 11,
  (103, '0'): 11,
  (103, '1'): 11,
  (103, '2'): 11,
  (103, '3'): 11,
  (103, '4'): 11,
  (103, '5'): 11,
  (103, '6'): 11,
  (103, '7'): 11,
  (103, '8'): 11,
  (103, '9'): 11,
  (103, 'A'): 11,
  (103, 'B'): 11,
  (103, 'C'): 11,
  (103, 'D'): 11,
  (103, 'E'): 11,
  (103, 'F'): 11,
  (103, 'G'): 11,
  (103, 'H'): 11,
  (103, 'I'): 11,
  (103, 'J'): 11,
  (103, 'K'): 11,
  (103, 'L'): 11,
  (103, 'M'): 11,
  (103, 'N'): 11,
  (103, 'O'): 11,
  (103, 'P'): 11,
  (103, 'Q'): 11,
  (103, 'R'): 11,
  (103, 'S'): 11,
  (103, 'T'): 11,
  (103, 'U'): 11,
  (103, 'V'): 11,
  (103, 'W'): 11,
  (103, 'X'): 11,
  (103, 'Y'): 11,
  (103, 'Z'): 11,
  (103, '_'): 11,
  (103, 'a'): 11,
  (103, 'b'): 11,
  (103, 'c'): 11,
  (103, 'd'): 11,
  (103, 'e'): 11,
  (103, 'f'): 11,
  (103, 'g'): 11,
  (103, 'h'): 11,
  (103, 'i'): 11,
  (103, 'j'): 11,
  (103, 'k'): 11,
  (103, 'l'): 11,
  (103, 'm'): 11,
  (103, 'n'): 11,
  (103, 'o'): 11,
  (103, 'p'): 11,
  (103, 'q'): 11,
  (103, 'r'): 11,
  (103, 's'): 11,
  (103, 't'): 11,
  (103, 'u'): 11,
  (103, 'v'): 11,
  (103, 'w'): 11,
  (103, 'x'): 11,
  (103, 'y'): 11,
  (103, 'z'): 11,
  (109, '\x00'): 109,
  (109, '\x01'): 109,
  (109, '\x02'): 109,
  (109, '\x03'): 109,
  (109, '\x04'): 109,
  (109, '\x05'): 109,
  (109, '\x06'): 109,
  (109, '\x07'): 109,
  (109, '\x08'): 109,
  (109, '\t'): 109,
  (109, '\n'): 109,
  (109, '\x0b'): 109,
  (109, '\x0c'): 109,
  (109, '\r'): 109,
  (109, '\x0e'): 109,
  (109, '\x0f'): 109,
  (109, '\x10'): 109,
  (109, '\x11'): 109,
  (109, '\x12'): 109,
  (109, '\x13'): 109,
  (109, '\x14'): 109,
  (109, '\x15'): 109,
  (109, '\x16'): 109,
  (109, '\x17'): 109,
  (109, '\x18'): 109,
  (109, '\x19'): 109,
  (109, '\x1a'): 109,
  (109, '\x1b'): 109,
  (109, '\x1c'): 109,
  (109, '\x1d'): 109,
  (109, '\x1e'): 109,
  (109, '\x1f'): 109,
  (109, ' '): 109,
  (109, '!'): 109,
  (109, '"'): 109,
  (109, '#'): 109,
  (109, '$'): 109,
  (109, '%'): 109,
  (109, '&'): 109,
  (109, "'"): 109,
  (109, '('): 109,
  (109, ')'): 109,
  (109, '*'): 112,
  (109, '+'): 109,
  (109, ','): 109,
  (109, '-'): 109,
  (109, '.'): 109,
  (109, '/'): 109,
  (109, '0'): 109,
  (109, '1'): 109,
  (109, '2'): 109,
  (109, '3'): 109,
  (109, '4'): 109,
  (109, '5'): 109,
  (109, '6'): 109,
  (109, '7'): 109,
  (109, '8'): 109,
  (109, '9'): 109,
  (109, ':'): 109,
  (109, ';'): 109,
  (109, '<'): 109,
  (109, '='): 109,
  (109, '>'): 109,
  (109, '?'): 109,
  (109, '@'): 109,
  (109, 'A'): 109,
  (109, 'B'): 109,
  (109, 'C'): 109,
  (109, 'D'): 109,
  (109, 'E'): 109,
  (109, 'F'): 109,
  (109, 'G'): 109,
  (109, 'H'): 109,
  (109, 'I'): 109,
  (109, 'J'): 109,
  (109, 'K'): 109,
  (109, 'L'): 109,
  (109, 'M'): 109,
  (109, 'N'): 109,
  (109, 'O'): 109,
  (109, 'P'): 109,
  (109, 'Q'): 109,
  (109, 'R'): 109,
  (109, 'S'): 109,
  (109, 'T'): 109,
  (109, 'U'): 109,
  (109, 'V'): 109,
  (109, 'W'): 109,
  (109, 'X'): 109,
  (109, 'Y'): 109,
  (109, 'Z'): 109,
  (109, '['): 109,
  (109, '\\'): 109,
  (109, ']'): 109,
  (109, '^'): 109,
  (109, '_'): 109,
  (109, '`'): 109,
  (109, 'a'): 109,
  (109, 'b'): 109,
  (109, 'c'): 109,
  (109, 'd'): 109,
  (109, 'e'): 109,
  (109, 'f'): 109,
  (109, 'g'): 109,
  (109, 'h'): 109,
  (109, 'i'): 109,
  (109, 'j'): 109,
  (109, 'k'): 109,
  (109, 'l'): 109,
  (109, 'm'): 109,
  (109, 'n'): 109,
  (109, 'o'): 109,
  (109, 'p'): 109,
  (109, 'q'): 109,
  (109, 'r'): 109,
  (109, 's'): 109,
  (109, 't'): 109,
  (109, 'u'): 109,
  (109, 'v'): 109,
  (109, 'w'): 109,
  (109, 'x'): 109,
  (109, 'y'): 109,
  (109, 'z'): 109,
  (109, '{'): 109,
  (109, '|'): 109,
  (109, '}'): 109,
  (109, '~'): 109,
  (109, '\x7f'): 109,
  (109, '\x80'): 109,
  (109, '\x81'): 109,
  (109, '\x82'): 109,
  (109, '\x83'): 109,
  (109, '\x84'): 109,
  (109, '\x85'): 109,
  (109, '\x86'): 109,
  (109, '\x87'): 109,
  (109, '\x88'): 109,
  (109, '\x89'): 109,
  (109, '\x8a'): 109,
  (109, '\x8b'): 109,
  (109, '\x8c'): 109,
  (109, '\x8d'): 109,
  (109, '\x8e'): 109,
  (109, '\x8f'): 109,
  (109, '\x90'): 109,
  (109, '\x91'): 109,
  (109, '\x92'): 109,
  (109, '\x93'): 109,
  (109, '\x94'): 109,
  (109, '\x95'): 109,
  (109, '\x96'): 109,
  (109, '\x97'): 109,
  (109, '\x98'): 109,
  (109, '\x99'): 109,
  (109, '\x9a'): 109,
  (109, '\x9b'): 109,
  (109, '\x9c'): 109,
  (109, '\x9d'): 109,
  (109, '\x9e'): 109,
  (109, '\x9f'): 109,
  (109, '\xa0'): 109,
  (109, '\xa1'): 109,
  (109, '\xa2'): 109,
  (109, '\xa3'): 109,
  (109, '\xa4'): 109,
  (109, '\xa5'): 109,
  (109, '\xa6'): 109,
  (109, '\xa7'): 109,
  (109, '\xa8'): 109,
  (109, '\xa9'): 109,
  (109, '\xaa'): 109,
  (109, '\xab'): 109,
  (109, '\xac'): 109,
  (109, '\xad'): 109,
  (109, '\xae'): 109,
  (109, '\xaf'): 109,
  (109, '\xb0'): 109,
  (109, '\xb1'): 109,
  (109, '\xb2'): 109,
  (109, '\xb3'): 109,
  (109, '\xb4'): 109,
  (109, '\xb5'): 109,
  (109, '\xb6'): 109,
  (109, '\xb7'): 109,
  (109, '\xb8'): 109,
  (109, '\xb9'): 109,
  (109, '\xba'): 109,
  (109, '\xbb'): 109,
  (109, '\xbc'): 109,
  (109, '\xbd'): 109,
  (109, '\xbe'): 109,
  (109, '\xbf'): 109,
  (109, '\xc0'): 109,
  (109, '\xc1'): 109,
  (109, '\xc2'): 109,
  (109, '\xc3'): 109,
  (109, '\xc4'): 109,
  (109, '\xc5'): 109,
  (109, '\xc6'): 109,
  (109, '\xc7'): 109,
  (109, '\xc8'): 109,
  (109, '\xc9'): 109,
  (109, '\xca'): 109,
  (109, '\xcb'): 109,
  (109, '\xcc'): 109,
  (109, '\xcd'): 109,
  (109, '\xce'): 109,
  (109, '\xcf'): 109,
  (109, '\xd0'): 109,
  (109, '\xd1'): 109,
  (109, '\xd2'): 109,
  (109, '\xd3'): 109,
  (109, '\xd4'): 109,
  (109, '\xd5'): 109,
  (109, '\xd6'): 109,
  (109, '\xd7'): 109,
  (109, '\xd8'): 109,
  (109, '\xd9'): 109,
  (109, '\xda'): 109,
  (109, '\xdb'): 109,
  (109, '\xdc'): 109,
  (109, '\xdd'): 109,
  (109, '\xde'): 109,
  (109, '\xdf'): 109,
  (109, '\xe0'): 109,
  (109, '\xe1'): 109,
  (109, '\xe2'): 109,
  (109, '\xe3'): 109,
  (109, '\xe4'): 109,
  (109, '\xe5'): 109,
  (109, '\xe6'): 109,
  (109, '\xe7'): 109,
  (109, '\xe8'): 109,
  (109, '\xe9'): 109,
  (109, '\xea'): 109,
  (109, '\xeb'): 109,
  (109, '\xec'): 109,
  (109, '\xed'): 109,
  (109, '\xee'): 109,
  (109, '\xef'): 109,
  (109, '\xf0'): 109,
  (109, '\xf1'): 109,
  (109, '\xf2'): 109,
  (109, '\xf3'): 109,
  (109, '\xf4'): 109,
  (109, '\xf5'): 109,
  (109, '\xf6'): 109,
  (109, '\xf7'): 109,
  (109, '\xf8'): 109,
  (109, '\xf9'): 109,
  (109, '\xfa'): 109,
  (109, '\xfb'): 109,
  (109, '\xfc'): 109,
  (109, '\xfd'): 109,
  (109, '\xfe'): 109,
  (109, '\xff'): 109,
  (112, '\x00'): 109,
  (112, '\x01'): 109,
  (112, '\x02'): 109,
  (112, '\x03'): 109,
  (112, '\x04'): 109,
  (112, '\x05'): 109,
  (112, '\x06'): 109,
  (112, '\x07'): 109,
  (112, '\x08'): 109,
  (112, '\t'): 109,
  (112, '\n'): 109,
  (112, '\x0b'): 109,
  (112, '\x0c'): 109,
  (112, '\r'): 109,
  (112, '\x0e'): 109,
  (112, '\x0f'): 109,
  (112, '\x10'): 109,
  (112, '\x11'): 109,
  (112, '\x12'): 109,
  (112, '\x13'): 109,
  (112, '\x14'): 109,
  (112, '\x15'): 109,
  (112, '\x16'): 109,
  (112, '\x17'): 109,
  (112, '\x18'): 109,
  (112, '\x19'): 109,
  (112, '\x1a'): 109,
  (112, '\x1b'): 109,
  (112, '\x1c'): 109,
  (112, '\x1d'): 109,
  (112, '\x1e'): 109,
  (112, '\x1f'): 109,
  (112, ' '): 109,
  (112, '!'): 109,
  (112, '"'): 109,
  (112, '#'): 109,
  (112, '$'): 109,
  (112, '%'): 109,
  (112, '&'): 109,
  (112, "'"): 109,
  (112, '('): 109,
  (112, ')'): 109,
  (112, '*'): 109,
  (112, '+'): 109,
  (112, ','): 109,
  (112, '-'): 109,
  (112, '.'): 109,
  (112, '/'): 1,
  (112, '0'): 109,
  (112, '1'): 109,
  (112, '2'): 109,
  (112, '3'): 109,
  (112, '4'): 109,
  (112, '5'): 109,
  (112, '6'): 109,
  (112, '7'): 109,
  (112, '8'): 109,
  (112, '9'): 109,
  (112, ':'): 109,
  (112, ';'): 109,
  (112, '<'): 109,
  (112, '='): 109,
  (112, '>'): 109,
  (112, '?'): 109,
  (112, '@'): 109,
  (112, 'A'): 109,
  (112, 'B'): 109,
  (112, 'C'): 109,
  (112, 'D'): 109,
  (112, 'E'): 109,
  (112, 'F'): 109,
  (112, 'G'): 109,
  (112, 'H'): 109,
  (112, 'I'): 109,
  (112, 'J'): 109,
  (112, 'K'): 109,
  (112, 'L'): 109,
  (112, 'M'): 109,
  (112, 'N'): 109,
  (112, 'O'): 109,
  (112, 'P'): 109,
  (112, 'Q'): 109,
  (112, 'R'): 109,
  (112, 'S'): 109,
  (112, 'T'): 109,
  (112, 'U'): 109,
  (112, 'V'): 109,
  (112, 'W'): 109,
  (112, 'X'): 109,
  (112, 'Y'): 109,
  (112, 'Z'): 109,
  (112, '['): 109,
  (112, '\\'): 109,
  (112, ']'): 109,
  (112, '^'): 109,
  (112, '_'): 109,
  (112, '`'): 109,
  (112, 'a'): 109,
  (112, 'b'): 109,
  (112, 'c'): 109,
  (112, 'd'): 109,
  (112, 'e'): 109,
  (112, 'f'): 109,
  (112, 'g'): 109,
  (112, 'h'): 109,
  (112, 'i'): 109,
  (112, 'j'): 109,
  (112, 'k'): 109,
  (112, 'l'): 109,
  (112, 'm'): 109,
  (112, 'n'): 109,
  (112, 'o'): 109,
  (112, 'p'): 109,
  (112, 'q'): 109,
  (112, 'r'): 109,
  (112, 's'): 109,
  (112, 't'): 109,
  (112, 'u'): 109,
  (112, 'v'): 109,
  (112, 'w'): 109,
  (112, 'x'): 109,
  (112, 'y'): 109,
  (112, 'z'): 109,
  (112, '{'): 109,
  (112, '|'): 109,
  (112, '}'): 109,
  (112, '~'): 109,
  (112, '\x7f'): 109,
  (112, '\x80'): 109,
  (112, '\x81'): 109,
  (112, '\x82'): 109,
  (112, '\x83'): 109,
  (112, '\x84'): 109,
  (112, '\x85'): 109,
  (112, '\x86'): 109,
  (112, '\x87'): 109,
  (112, '\x88'): 109,
  (112, '\x89'): 109,
  (112, '\x8a'): 109,
  (112, '\x8b'): 109,
  (112, '\x8c'): 109,
  (112, '\x8d'): 109,
  (112, '\x8e'): 109,
  (112, '\x8f'): 109,
  (112, '\x90'): 109,
  (112, '\x91'): 109,
  (112, '\x92'): 109,
  (112, '\x93'): 109,
  (112, '\x94'): 109,
  (112, '\x95'): 109,
  (112, '\x96'): 109,
  (112, '\x97'): 109,
  (112, '\x98'): 109,
  (112, '\x99'): 109,
  (112, '\x9a'): 109,
  (112, '\x9b'): 109,
  (112, '\x9c'): 109,
  (112, '\x9d'): 109,
  (112, '\x9e'): 109,
  (112, '\x9f'): 109,
  (112, '\xa0'): 109,
  (112, '\xa1'): 109,
  (112, '\xa2'): 109,
  (112, '\xa3'): 109,
  (112, '\xa4'): 109,
  (112, '\xa5'): 109,
  (112, '\xa6'): 109,
  (112, '\xa7'): 109,
  (112, '\xa8'): 109,
  (112, '\xa9'): 109,
  (112, '\xaa'): 109,
  (112, '\xab'): 109,
  (112, '\xac'): 109,
  (112, '\xad'): 109,
  (112, '\xae'): 109,
  (112, '\xaf'): 109,
  (112, '\xb0'): 109,
  (112, '\xb1'): 109,
  (112, '\xb2'): 109,
  (112, '\xb3'): 109,
  (112, '\xb4'): 109,
  (112, '\xb5'): 109,
  (112, '\xb6'): 109,
  (112, '\xb7'): 109,
  (112, '\xb8'): 109,
  (112, '\xb9'): 109,
  (112, '\xba'): 109,
  (112, '\xbb'): 109,
  (112, '\xbc'): 109,
  (112, '\xbd'): 109,
  (112, '\xbe'): 109,
  (112, '\xbf'): 109,
  (112, '\xc0'): 109,
  (112, '\xc1'): 109,
  (112, '\xc2'): 109,
  (112, '\xc3'): 109,
  (112, '\xc4'): 109,
  (112, '\xc5'): 109,
  (112, '\xc6'): 109,
  (112, '\xc7'): 109,
  (112, '\xc8'): 109,
  (112, '\xc9'): 109,
  (112, '\xca'): 109,
  (112, '\xcb'): 109,
  (112, '\xcc'): 109,
  (112, '\xcd'): 109,
  (112, '\xce'): 109,
  (112, '\xcf'): 109,
  (112, '\xd0'): 109,
  (112, '\xd1'): 109,
  (112, '\xd2'): 109,
  (112, '\xd3'): 109,
  (112, '\xd4'): 109,
  (112, '\xd5'): 109,
  (112, '\xd6'): 109,
  (112, '\xd7'): 109,
  (112, '\xd8'): 109,
  (112, '\xd9'): 109,
  (112, '\xda'): 109,
  (112, '\xdb'): 109,
  (112, '\xdc'): 109,
  (112, '\xdd'): 109,
  (112, '\xde'): 109,
  (112, '\xdf'): 109,
  (112, '\xe0'): 109,
  (112, '\xe1'): 109,
  (112, '\xe2'): 109,
  (112, '\xe3'): 109,
  (112, '\xe4'): 109,
  (112, '\xe5'): 109,
  (112, '\xe6'): 109,
  (112, '\xe7'): 109,
  (112, '\xe8'): 109,
  (112, '\xe9'): 109,
  (112, '\xea'): 109,
  (112, '\xeb'): 109,
  (112, '\xec'): 109,
  (112, '\xed'): 109,
  (112, '\xee'): 109,
  (112, '\xef'): 109,
  (112, '\xf0'): 109,
  (112, '\xf1'): 109,
  (112, '\xf2'): 109,
  (112, '\xf3'): 109,
  (112, '\xf4'): 109,
  (112, '\xf5'): 109,
  (112, '\xf6'): 109,
  (112, '\xf7'): 109,
  (112, '\xf8'): 109,
  (112, '\xf9'): 109,
  (112, '\xfa'): 109,
  (112, '\xfb'): 109,
  (112, '\xfc'): 109,
  (112, '\xfd'): 109,
  (112, '\xfe'): 109,
  (112, '\xff'): 109,
  (113, '0'): 11,
  (113, '1'): 11,
  (113, '2'): 11,
  (113, '3'): 11,
  (113, '4'): 11,
  (113, '5'): 11,
  (113, '6'): 11,
  (113, '7'): 11,
  (113, '8'): 11,
  (113, '9'): 11,
  (113, 'A'): 11,
  (113, 'B'): 11,
  (113, 'C'): 11,
  (113, 'D'): 11,
  (113, 'E'): 11,
  (113, 'F'): 11,
  (113, 'G'): 11,
  (113, 'H'): 11,
  (113, 'I'): 11,
  (113, 'J'): 11,
  (113, 'K'): 11,
  (113, 'L'): 11,
  (113, 'M'): 11,
  (113, 'N'): 11,
  (113, 'O'): 11,
  (113, 'P'): 11,
  (113, 'Q'): 11,
  (113, 'R'): 11,
  (113, 'S'): 11,
  (113, 'T'): 11,
  (113, 'U'): 11,
  (113, 'V'): 11,
  (113, 'W'): 11,
  (113, 'X'): 11,
  (113, 'Y'): 11,
  (113, 'Z'): 11,
  (113, '_'): 11,
  (113, 'a'): 11,
  (113, 'b'): 11,
  (113, 'c'): 11,
  (113, 'd'): 11,
  (113, 'e'): 11,
  (113, 'f'): 11,
  (113, 'g'): 11,
  (113, 'h'): 11,
  (113, 'i'): 11,
  (113, 'j'): 11,
  (113, 'k'): 11,
  (113, 'l'): 11,
  (113, 'm'): 11,
  (113, 'n'): 11,
  (113, 'o'): 11,
  (113, 'p'): 11,
  (113, 'q'): 11,
  (113, 'r'): 114,
  (113, 's'): 11,
  (113, 't'): 11,
  (113, 'u'): 11,
  (113, 'v'): 11,
  (113, 'w'): 11,
  (113, 'x'): 11,
  (113, 'y'): 11,
  (113, 'z'): 11,
  (114, '0'): 11,
  (114, '1'): 11,
  (114, '2'): 11,
  (114, '3'): 11,
  (114, '4'): 11,
  (114, '5'): 11,
  (114, '6'): 11,
  (114, '7'): 11,
  (114, '8'): 11,
  (114, '9'): 11,
  (114, 'A'): 11,
  (114, 'B'): 11,
  (114, 'C'): 11,
  (114, 'D'): 11,
  (114, 'E'): 11,
  (114, 'F'): 11,
  (114, 'G'): 11,
  (114, 'H'): 11,
  (114, 'I'): 11,
  (114, 'J'): 11,
  (114, 'K'): 11,
  (114, 'L'): 11,
  (114, 'M'): 11,
  (114, 'N'): 11,
  (114, 'O'): 11,
  (114, 'P'): 11,
  (114, 'Q'): 11,
  (114, 'R'): 11,
  (114, 'S'): 11,
  (114, 'T'): 11,
  (114, 'U'): 11,
  (114, 'V'): 11,
  (114, 'W'): 11,
  (114, 'X'): 11,
  (114, 'Y'): 11,
  (114, 'Z'): 11,
  (114, '_'): 11,
  (114, 'a'): 11,
  (114, 'b'): 11,
  (114, 'c'): 11,
  (114, 'd'): 11,
  (114, 'e'): 11,
  (114, 'f'): 11,
  (114, 'g'): 11,
  (114, 'h'): 11,
  (114, 'i'): 11,
  (114, 'j'): 11,
  (114, 'k'): 11,
  (114, 'l'): 11,
  (114, 'm'): 11,
  (114, 'n'): 11,
  (114, 'o'): 11,
  (114, 'p'): 11,
  (114, 'q'): 11,
  (114, 'r'): 11,
  (114, 's'): 11,
  (114, 't'): 11,
  (114, 'u'): 11,
  (114, 'v'): 11,
  (114, 'w'): 11,
  (114, 'x'): 11,
  (114, 'y'): 11,
  (114, 'z'): 11,
  (115, '0'): 11,
  (115, '1'): 11,
  (115, '2'): 11,
  (115, '3'): 11,
  (115, '4'): 11,
  (115, '5'): 11,
  (115, '6'): 11,
  (115, '7'): 11,
  (115, '8'): 11,
  (115, '9'): 11,
  (115, 'A'): 11,
  (115, 'B'): 11,
  (115, 'C'): 11,
  (115, 'D'): 11,
  (115, 'E'): 11,
  (115, 'F'): 11,
  (115, 'G'): 11,
  (115, 'H'): 11,
  (115, 'I'): 11,
  (115, 'J'): 11,
  (115, 'K'): 11,
  (115, 'L'): 11,
  (115, 'M'): 11,
  (115, 'N'): 11,
  (115, 'O'): 11,
  (115, 'P'): 11,
  (115, 'Q'): 11,
  (115, 'R'): 11,
  (115, 'S'): 11,
  (115, 'T'): 11,
  (115, 'U'): 11,
  (115, 'V'): 11,
  (115, 'W'): 11,
  (115, 'X'): 11,
  (115, 'Y'): 11,
  (115, 'Z'): 11,
  (115, '_'): 11,
  (115, 'a'): 11,
  (115, 'b'): 11,
  (115, 'c'): 11,
  (115, 'd'): 11,
  (115, 'e'): 11,
  (115, 'f'): 11,
  (115, 'g'): 11,
  (115, 'h'): 11,
  (115, 'i'): 11,
  (115, 'j'): 11,
  (115, 'k'): 11,
  (115, 'l'): 11,
  (115, 'm'): 11,
  (115, 'n'): 11,
  (115, 'o'): 11,
  (115, 'p'): 11,
  (115, 'q'): 11,
  (115, 'r'): 11,
  (115, 's'): 122,
  (115, 't'): 11,
  (115, 'u'): 11,
  (115, 'v'): 11,
  (115, 'w'): 11,
  (115, 'x'): 11,
  (115, 'y'): 11,
  (115, 'z'): 11,
  (116, '0'): 11,
  (116, '1'): 11,
  (116, '2'): 11,
  (116, '3'): 11,
  (116, '4'): 11,
  (116, '5'): 11,
  (116, '6'): 11,
  (116, '7'): 11,
  (116, '8'): 11,
  (116, '9'): 11,
  (116, 'A'): 11,
  (116, 'B'): 11,
  (116, 'C'): 11,
  (116, 'D'): 11,
  (116, 'E'): 11,
  (116, 'F'): 11,
  (116, 'G'): 11,
  (116, 'H'): 11,
  (116, 'I'): 11,
  (116, 'J'): 11,
  (116, 'K'): 11,
  (116, 'L'): 11,
  (116, 'M'): 11,
  (116, 'N'): 11,
  (116, 'O'): 11,
  (116, 'P'): 11,
  (116, 'Q'): 11,
  (116, 'R'): 11,
  (116, 'S'): 11,
  (116, 'T'): 11,
  (116, 'U'): 11,
  (116, 'V'): 11,
  (116, 'W'): 11,
  (116, 'X'): 11,
  (116, 'Y'): 11,
  (116, 'Z'): 11,
  (116, '_'): 11,
  (116, 'a'): 11,
  (116, 'b'): 11,
  (116, 'c'): 11,
  (116, 'd'): 11,
  (116, 'e'): 11,
  (116, 'f'): 11,
  (116, 'g'): 11,
  (116, 'h'): 11,
  (116, 'i'): 11,
  (116, 'j'): 11,
  (116, 'k'): 11,
  (116, 'l'): 11,
  (116, 'm'): 11,
  (116, 'n'): 117,
  (116, 'o'): 11,
  (116, 'p'): 11,
  (116, 'q'): 11,
  (116, 'r'): 11,
  (116, 's'): 11,
  (116, 't'): 11,
  (116, 'u'): 11,
  (116, 'v'): 11,
  (116, 'w'): 11,
  (116, 'x'): 11,
  (116, 'y'): 11,
  (116, 'z'): 11,
  (117, '0'): 11,
  (117, '1'): 11,
  (117, '2'): 11,
  (117, '3'): 11,
  (117, '4'): 11,
  (117, '5'): 11,
  (117, '6'): 11,
  (117, '7'): 11,
  (117, '8'): 11,
  (117, '9'): 11,
  (117, 'A'): 11,
  (117, 'B'): 11,
  (117, 'C'): 11,
  (117, 'D'): 11,
  (117, 'E'): 11,
  (117, 'F'): 11,
  (117, 'G'): 11,
  (117, 'H'): 11,
  (117, 'I'): 11,
  (117, 'J'): 11,
  (117, 'K'): 11,
  (117, 'L'): 11,
  (117, 'M'): 11,
  (117, 'N'): 11,
  (117, 'O'): 11,
  (117, 'P'): 11,
  (117, 'Q'): 11,
  (117, 'R'): 11,
  (117, 'S'): 11,
  (117, 'T'): 11,
  (117, 'U'): 11,
  (117, 'V'): 11,
  (117, 'W'): 11,
  (117, 'X'): 11,
  (117, 'Y'): 11,
  (117, 'Z'): 11,
  (117, '_'): 11,
  (117, 'a'): 118,
  (117, 'b'): 11,
  (117, 'c'): 11,
  (117, 'd'): 11,
  (117, 'e'): 11,
  (117, 'f'): 11,
  (117, 'g'): 11,
  (117, 'h'): 11,
  (117, 'i'): 11,
  (117, 'j'): 11,
  (117, 'k'): 11,
  (117, 'l'): 11,
  (117, 'm'): 11,
  (117, 'n'): 11,
  (117, 'o'): 11,
  (117, 'p'): 11,
  (117, 'q'): 11,
  (117, 'r'): 11,
  (117, 's'): 11,
  (117, 't'): 11,
  (117, 'u'): 11,
  (117, 'v'): 11,
  (117, 'w'): 11,
  (117, 'x'): 11,
  (117, 'y'): 11,
  (117, 'z'): 11,
  (118, '0'): 11,
  (118, '1'): 11,
  (118, '2'): 11,
  (118, '3'): 11,
  (118, '4'): 11,
  (118, '5'): 11,
  (118, '6'): 11,
  (118, '7'): 11,
  (118, '8'): 11,
  (118, '9'): 11,
  (118, 'A'): 11,
  (118, 'B'): 11,
  (118, 'C'): 11,
  (118, 'D'): 11,
  (118, 'E'): 11,
  (118, 'F'): 11,
  (118, 'G'): 11,
  (118, 'H'): 11,
  (118, 'I'): 11,
  (118, 'J'): 11,
  (118, 'K'): 11,
  (118, 'L'): 11,
  (118, 'M'): 11,
  (118, 'N'): 11,
  (118, 'O'): 11,
  (118, 'P'): 11,
  (118, 'Q'): 11,
  (118, 'R'): 11,
  (118, 'S'): 11,
  (118, 'T'): 11,
  (118, 'U'): 11,
  (118, 'V'): 11,
  (118, 'W'): 11,
  (118, 'X'): 11,
  (118, 'Y'): 11,
  (118, 'Z'): 11,
  (118, '_'): 11,
  (118, 'a'): 11,
  (118, 'b'): 11,
  (118, 'c'): 11,
  (118, 'd'): 11,
  (118, 'e'): 11,
  (118, 'f'): 11,
  (118, 'g'): 11,
  (118, 'h'): 11,
  (118, 'i'): 11,
  (118, 'j'): 11,
  (118, 'k'): 11,
  (118, 'l'): 11,
  (118, 'm'): 119,
  (118, 'n'): 11,
  (118, 'o'): 11,
  (118, 'p'): 11,
  (118, 'q'): 11,
  (118, 'r'): 11,
  (118, 's'): 11,
  (118, 't'): 11,
  (118, 'u'): 11,
  (118, 'v'): 11,
  (118, 'w'): 11,
  (118, 'x'): 11,
  (118, 'y'): 11,
  (118, 'z'): 11,
  (119, '0'): 11,
  (119, '1'): 11,
  (119, '2'): 11,
  (119, '3'): 11,
  (119, '4'): 11,
  (119, '5'): 11,
  (119, '6'): 11,
  (119, '7'): 11,
  (119, '8'): 11,
  (119, '9'): 11,
  (119, 'A'): 11,
  (119, 'B'): 11,
  (119, 'C'): 11,
  (119, 'D'): 11,
  (119, 'E'): 11,
  (119, 'F'): 11,
  (119, 'G'): 11,
  (119, 'H'): 11,
  (119, 'I'): 11,
  (119, 'J'): 11,
  (119, 'K'): 11,
  (119, 'L'): 11,
  (119, 'M'): 11,
  (119, 'N'): 11,
  (119, 'O'): 11,
  (119, 'P'): 11,
  (119, 'Q'): 11,
  (119, 'R'): 11,
  (119, 'S'): 11,
  (119, 'T'): 11,
  (119, 'U'): 11,
  (119, 'V'): 11,
  (119, 'W'): 11,
  (119, 'X'): 11,
  (119, 'Y'): 11,
  (119, 'Z'): 11,
  (119, '_'): 11,
  (119, 'a'): 11,
  (119, 'b'): 11,
  (119, 'c'): 11,
  (119, 'd'): 11,
  (119, 'e'): 11,
  (119, 'f'): 11,
  (119, 'g'): 11,
  (119, 'h'): 11,
  (119, 'i'): 120,
  (119, 'j'): 11,
  (119, 'k'): 11,
  (119, 'l'): 11,
  (119, 'm'): 11,
  (119, 'n'): 11,
  (119, 'o'): 11,
  (119, 'p'): 11,
  (119, 'q'): 11,
  (119, 'r'): 11,
  (119, 's'): 11,
  (119, 't'): 11,
  (119, 'u'): 11,
  (119, 'v'): 11,
  (119, 'w'): 11,
  (119, 'x'): 11,
  (119, 'y'): 11,
  (119, 'z'): 11,
  (120, '0'): 11,
  (120, '1'): 11,
  (120, '2'): 11,
  (120, '3'): 11,
  (120, '4'): 11,
  (120, '5'): 11,
  (120, '6'): 11,
  (120, '7'): 11,
  (120, '8'): 11,
  (120, '9'): 11,
  (120, 'A'): 11,
  (120, 'B'): 11,
  (120, 'C'): 11,
  (120, 'D'): 11,
  (120, 'E'): 11,
  (120, 'F'): 11,
  (120, 'G'): 11,
  (120, 'H'): 11,
  (120, 'I'): 11,
  (120, 'J'): 11,
  (120, 'K'): 11,
  (120, 'L'): 11,
  (120, 'M'): 11,
  (120, 'N'): 11,
  (120, 'O'): 11,
  (120, 'P'): 11,
  (120, 'Q'): 11,
  (120, 'R'): 11,
  (120, 'S'): 11,
  (120, 'T'): 11,
  (120, 'U'): 11,
  (120, 'V'): 11,
  (120, 'W'): 11,
  (120, 'X'): 11,
  (120, 'Y'): 11,
  (120, 'Z'): 11,
  (120, '_'): 11,
  (120, 'a'): 11,
  (120, 'b'): 11,
  (120, 'c'): 121,
  (120, 'd'): 11,
  (120, 'e'): 11,
  (120, 'f'): 11,
  (120, 'g'): 11,
  (120, 'h'): 11,
  (120, 'i'): 11,
  (120, 'j'): 11,
  (120, 'k'): 11,
  (120, 'l'): 11,
  (120, 'm'): 11,
  (120, 'n'): 11,
  (120, 'o'): 11,
  (120, 'p'): 11,
  (120, 'q'): 11,
  (120, 'r'): 11,
  (120, 's'): 11,
  (120, 't'): 11,
  (120, 'u'): 11,
  (120, 'v'): 11,
  (120, 'w'): 11,
  (120, 'x'): 11,
  (120, 'y'): 11,
  (120, 'z'): 11,
  (121, '0'): 11,
  (121, '1'): 11,
  (121, '2'): 11,
  (121, '3'): 11,
  (121, '4'): 11,
  (121, '5'): 11,
  (121, '6'): 11,
  (121, '7'): 11,
  (121, '8'): 11,
  (121, '9'): 11,
  (121, 'A'): 11,
  (121, 'B'): 11,
  (121, 'C'): 11,
  (121, 'D'): 11,
  (121, 'E'): 11,
  (121, 'F'): 11,
  (121, 'G'): 11,
  (121, 'H'): 11,
  (121, 'I'): 11,
  (121, 'J'): 11,
  (121, 'K'): 11,
  (121, 'L'): 11,
  (121, 'M'): 11,
  (121, 'N'): 11,
  (121, 'O'): 11,
  (121, 'P'): 11,
  (121, 'Q'): 11,
  (121, 'R'): 11,
  (121, 'S'): 11,
  (121, 'T'): 11,
  (121, 'U'): 11,
  (121, 'V'): 11,
  (121, 'W'): 11,
  (121, 'X'): 11,
  (121, 'Y'): 11,
  (121, 'Z'): 11,
  (121, '_'): 11,
  (121, 'a'): 11,
  (121, 'b'): 11,
  (121, 'c'): 11,
  (121, 'd'): 11,
  (121, 'e'): 11,
  (121, 'f'): 11,
  (121, 'g'): 11,
  (121, 'h'): 11,
  (121, 'i'): 11,
  (121, 'j'): 11,
  (121, 'k'): 11,
  (121, 'l'): 11,
  (121, 'm'): 11,
  (121, 'n'): 11,
  (121, 'o'): 11,
  (121, 'p'): 11,
  (121, 'q'): 11,
  (121, 'r'): 11,
  (121, 's'): 11,
  (121, 't'): 11,
  (121, 'u'): 11,
  (121, 'v'): 11,
  (121, 'w'): 11,
  (121, 'x'): 11,
  (121, 'y'): 11,
  (121, 'z'): 11,
  (122, '0'): 11,
  (122, '1'): 11,
  (122, '2'): 11,
  (122, '3'): 11,
  (122, '4'): 11,
  (122, '5'): 11,
  (122, '6'): 11,
  (122, '7'): 11,
  (122, '8'): 11,
  (122, '9'): 11,
  (122, 'A'): 11,
  (122, 'B'): 11,
  (122, 'C'): 11,
  (122, 'D'): 11,
  (122, 'E'): 11,
  (122, 'F'): 11,
  (122, 'G'): 11,
  (122, 'H'): 11,
  (122, 'I'): 11,
  (122, 'J'): 11,
  (122, 'K'): 11,
  (122, 'L'): 11,
  (122, 'M'): 11,
  (122, 'N'): 11,
  (122, 'O'): 11,
  (122, 'P'): 11,
  (122, 'Q'): 11,
  (122, 'R'): 11,
  (122, 'S'): 11,
  (122, 'T'): 11,
  (122, 'U'): 11,
  (122, 'V'): 11,
  (122, 'W'): 11,
  (122, 'X'): 11,
  (122, 'Y'): 11,
  (122, 'Z'): 11,
  (122, '_'): 11,
  (122, 'a'): 11,
  (122, 'b'): 11,
  (122, 'c'): 123,
  (122, 'd'): 11,
  (122, 'e'): 11,
  (122, 'f'): 11,
  (122, 'g'): 11,
  (122, 'h'): 11,
  (122, 'i'): 11,
  (122, 'j'): 11,
  (122, 'k'): 11,
  (122, 'l'): 11,
  (122, 'm'): 11,
  (122, 'n'): 11,
  (122, 'o'): 11,
  (122, 'p'): 11,
  (122, 'q'): 11,
  (122, 'r'): 11,
  (122, 's'): 11,
  (122, 't'): 11,
  (122, 'u'): 11,
  (122, 'v'): 11,
  (122, 'w'): 11,
  (122, 'x'): 11,
  (122, 'y'): 11,
  (122, 'z'): 11,
  (123, '0'): 11,
  (123, '1'): 11,
  (123, '2'): 11,
  (123, '3'): 11,
  (123, '4'): 11,
  (123, '5'): 11,
  (123, '6'): 11,
  (123, '7'): 11,
  (123, '8'): 11,
  (123, '9'): 11,
  (123, 'A'): 11,
  (123, 'B'): 11,
  (123, 'C'): 11,
  (123, 'D'): 11,
  (123, 'E'): 11,
  (123, 'F'): 11,
  (123, 'G'): 11,
  (123, 'H'): 11,
  (123, 'I'): 11,
  (123, 'J'): 11,
  (123, 'K'): 11,
  (123, 'L'): 11,
  (123, 'M'): 11,
  (123, 'N'): 11,
  (123, 'O'): 11,
  (123, 'P'): 11,
  (123, 'Q'): 11,
  (123, 'R'): 11,
  (123, 'S'): 11,
  (123, 'T'): 11,
  (123, 'U'): 11,
  (123, 'V'): 11,
  (123, 'W'): 11,
  (123, 'X'): 11,
  (123, 'Y'): 11,
  (123, 'Z'): 11,
  (123, '_'): 11,
  (123, 'a'): 11,
  (123, 'b'): 11,
  (123, 'c'): 11,
  (123, 'd'): 11,
  (123, 'e'): 11,
  (123, 'f'): 11,
  (123, 'g'): 11,
  (123, 'h'): 11,
  (123, 'i'): 11,
  (123, 'j'): 11,
  (123, 'k'): 11,
  (123, 'l'): 11,
  (123, 'm'): 11,
  (123, 'n'): 11,
  (123, 'o'): 124,
  (123, 'p'): 11,
  (123, 'q'): 11,
  (123, 'r'): 11,
  (123, 's'): 11,
  (123, 't'): 11,
  (123, 'u'): 11,
  (123, 'v'): 11,
  (123, 'w'): 11,
  (123, 'x'): 11,
  (123, 'y'): 11,
  (123, 'z'): 11,
  (124, '0'): 11,
  (124, '1'): 11,
  (124, '2'): 11,
  (124, '3'): 11,
  (124, '4'): 11,
  (124, '5'): 11,
  (124, '6'): 11,
  (124, '7'): 11,
  (124, '8'): 11,
  (124, '9'): 11,
  (124, 'A'): 11,
  (124, 'B'): 11,
  (124, 'C'): 11,
  (124, 'D'): 11,
  (124, 'E'): 11,
  (124, 'F'): 11,
  (124, 'G'): 11,
  (124, 'H'): 11,
  (124, 'I'): 11,
  (124, 'J'): 11,
  (124, 'K'): 11,
  (124, 'L'): 11,
  (124, 'M'): 11,
  (124, 'N'): 11,
  (124, 'O'): 11,
  (124, 'P'): 11,
  (124, 'Q'): 11,
  (124, 'R'): 11,
  (124, 'S'): 11,
  (124, 'T'): 11,
  (124, 'U'): 11,
  (124, 'V'): 11,
  (124, 'W'): 11,
  (124, 'X'): 11,
  (124, 'Y'): 11,
  (124, 'Z'): 11,
  (124, '_'): 11,
  (124, 'a'): 11,
  (124, 'b'): 11,
  (124, 'c'): 11,
  (124, 'd'): 11,
  (124, 'e'): 11,
  (124, 'f'): 11,
  (124, 'g'): 11,
  (124, 'h'): 11,
  (124, 'i'): 11,
  (124, 'j'): 11,
  (124, 'k'): 11,
  (124, 'l'): 11,
  (124, 'm'): 11,
  (124, 'n'): 125,
  (124, 'o'): 11,
  (124, 'p'): 11,
  (124, 'q'): 11,
  (124, 'r'): 11,
  (124, 's'): 11,
  (124, 't'): 11,
  (124, 'u'): 11,
  (124, 'v'): 11,
  (124, 'w'): 11,
  (124, 'x'): 11,
  (124, 'y'): 11,
  (124, 'z'): 11,
  (125, '0'): 11,
  (125, '1'): 11,
  (125, '2'): 11,
  (125, '3'): 11,
  (125, '4'): 11,
  (125, '5'): 11,
  (125, '6'): 11,
  (125, '7'): 11,
  (125, '8'): 11,
  (125, '9'): 11,
  (125, 'A'): 11,
  (125, 'B'): 11,
  (125, 'C'): 11,
  (125, 'D'): 11,
  (125, 'E'): 11,
  (125, 'F'): 11,
  (125, 'G'): 11,
  (125, 'H'): 11,
  (125, 'I'): 11,
  (125, 'J'): 11,
  (125, 'K'): 11,
  (125, 'L'): 11,
  (125, 'M'): 11,
  (125, 'N'): 11,
  (125, 'O'): 11,
  (125, 'P'): 11,
  (125, 'Q'): 11,
  (125, 'R'): 11,
  (125, 'S'): 11,
  (125, 'T'): 11,
  (125, 'U'): 11,
  (125, 'V'): 11,
  (125, 'W'): 11,
  (125, 'X'): 11,
  (125, 'Y'): 11,
  (125, 'Z'): 11,
  (125, '_'): 11,
  (125, 'a'): 11,
  (125, 'b'): 11,
  (125, 'c'): 11,
  (125, 'd'): 11,
  (125, 'e'): 11,
  (125, 'f'): 11,
  (125, 'g'): 11,
  (125, 'h'): 11,
  (125, 'i'): 11,
  (125, 'j'): 11,
  (125, 'k'): 11,
  (125, 'l'): 11,
  (125, 'm'): 11,
  (125, 'n'): 11,
  (125, 'o'): 11,
  (125, 'p'): 11,
  (125, 'q'): 11,
  (125, 'r'): 11,
  (125, 's'): 11,
  (125, 't'): 126,
  (125, 'u'): 11,
  (125, 'v'): 11,
  (125, 'w'): 11,
  (125, 'x'): 11,
  (125, 'y'): 11,
  (125, 'z'): 11,
  (126, '0'): 11,
  (126, '1'): 11,
  (126, '2'): 11,
  (126, '3'): 11,
  (126, '4'): 11,
  (126, '5'): 11,
  (126, '6'): 11,
  (126, '7'): 11,
  (126, '8'): 11,
  (126, '9'): 11,
  (126, 'A'): 11,
  (126, 'B'): 11,
  (126, 'C'): 11,
  (126, 'D'): 11,
  (126, 'E'): 11,
  (126, 'F'): 11,
  (126, 'G'): 11,
  (126, 'H'): 11,
  (126, 'I'): 11,
  (126, 'J'): 11,
  (126, 'K'): 11,
  (126, 'L'): 11,
  (126, 'M'): 11,
  (126, 'N'): 11,
  (126, 'O'): 11,
  (126, 'P'): 11,
  (126, 'Q'): 11,
  (126, 'R'): 11,
  (126, 'S'): 11,
  (126, 'T'): 11,
  (126, 'U'): 11,
  (126, 'V'): 11,
  (126, 'W'): 11,
  (126, 'X'): 11,
  (126, 'Y'): 11,
  (126, 'Z'): 11,
  (126, '_'): 11,
  (126, 'a'): 11,
  (126, 'b'): 11,
  (126, 'c'): 11,
  (126, 'd'): 11,
  (126, 'e'): 11,
  (126, 'f'): 11,
  (126, 'g'): 11,
  (126, 'h'): 11,
  (126, 'i'): 127,
  (126, 'j'): 11,
  (126, 'k'): 11,
  (126, 'l'): 11,
  (126, 'm'): 11,
  (126, 'n'): 11,
  (126, 'o'): 11,
  (126, 'p'): 11,
  (126, 'q'): 11,
  (126, 'r'): 11,
  (126, 's'): 11,
  (126, 't'): 11,
  (126, 'u'): 11,
  (126, 'v'): 11,
  (126, 'w'): 11,
  (126, 'x'): 11,
  (126, 'y'): 11,
  (126, 'z'): 11,
  (127, '0'): 11,
  (127, '1'): 11,
  (127, '2'): 11,
  (127, '3'): 11,
  (127, '4'): 11,
  (127, '5'): 11,
  (127, '6'): 11,
  (127, '7'): 11,
  (127, '8'): 11,
  (127, '9'): 11,
  (127, 'A'): 11,
  (127, 'B'): 11,
  (127, 'C'): 11,
  (127, 'D'): 11,
  (127, 'E'): 11,
  (127, 'F'): 11,
  (127, 'G'): 11,
  (127, 'H'): 11,
  (127, 'I'): 11,
  (127, 'J'): 11,
  (127, 'K'): 11,
  (127, 'L'): 11,
  (127, 'M'): 11,
  (127, 'N'): 11,
  (127, 'O'): 11,
  (127, 'P'): 11,
  (127, 'Q'): 11,
  (127, 'R'): 11,
  (127, 'S'): 11,
  (127, 'T'): 11,
  (127, 'U'): 11,
  (127, 'V'): 11,
  (127, 'W'): 11,
  (127, 'X'): 11,
  (127, 'Y'): 11,
  (127, 'Z'): 11,
  (127, '_'): 11,
  (127, 'a'): 11,
  (127, 'b'): 11,
  (127, 'c'): 11,
  (127, 'd'): 11,
  (127, 'e'): 11,
  (127, 'f'): 11,
  (127, 'g'): 128,
  (127, 'h'): 11,
  (127, 'i'): 11,
  (127, 'j'): 11,
  (127, 'k'): 11,
  (127, 'l'): 11,
  (127, 'm'): 11,
  (127, 'n'): 11,
  (127, 'o'): 11,
  (127, 'p'): 11,
  (127, 'q'): 11,
  (127, 'r'): 11,
  (127, 's'): 11,
  (127, 't'): 11,
  (127, 'u'): 11,
  (127, 'v'): 11,
  (127, 'w'): 11,
  (127, 'x'): 11,
  (127, 'y'): 11,
  (127, 'z'): 11,
  (128, '0'): 11,
  (128, '1'): 11,
  (128, '2'): 11,
  (128, '3'): 11,
  (128, '4'): 11,
  (128, '5'): 11,
  (128, '6'): 11,
  (128, '7'): 11,
  (128, '8'): 11,
  (128, '9'): 11,
  (128, 'A'): 11,
  (128, 'B'): 11,
  (128, 'C'): 11,
  (128, 'D'): 11,
  (128, 'E'): 11,
  (128, 'F'): 11,
  (128, 'G'): 11,
  (128, 'H'): 11,
  (128, 'I'): 11,
  (128, 'J'): 11,
  (128, 'K'): 11,
  (128, 'L'): 11,
  (128, 'M'): 11,
  (128, 'N'): 11,
  (128, 'O'): 11,
  (128, 'P'): 11,
  (128, 'Q'): 11,
  (128, 'R'): 11,
  (128, 'S'): 11,
  (128, 'T'): 11,
  (128, 'U'): 11,
  (128, 'V'): 11,
  (128, 'W'): 11,
  (128, 'X'): 11,
  (128, 'Y'): 11,
  (128, 'Z'): 11,
  (128, '_'): 11,
  (128, 'a'): 11,
  (128, 'b'): 11,
  (128, 'c'): 11,
  (128, 'd'): 11,
  (128, 'e'): 11,
  (128, 'f'): 11,
  (128, 'g'): 11,
  (128, 'h'): 11,
  (128, 'i'): 11,
  (128, 'j'): 11,
  (128, 'k'): 11,
  (128, 'l'): 11,
  (128, 'm'): 11,
  (128, 'n'): 11,
  (128, 'o'): 11,
  (128, 'p'): 11,
  (128, 'q'): 11,
  (128, 'r'): 11,
  (128, 's'): 11,
  (128, 't'): 11,
  (128, 'u'): 129,
  (128, 'v'): 11,
  (128, 'w'): 11,
  (128, 'x'): 11,
  (128, 'y'): 11,
  (128, 'z'): 11,
  (129, '0'): 11,
  (129, '1'): 11,
  (129, '2'): 11,
  (129, '3'): 11,
  (129, '4'): 11,
  (129, '5'): 11,
  (129, '6'): 11,
  (129, '7'): 11,
  (129, '8'): 11,
  (129, '9'): 11,
  (129, 'A'): 11,
  (129, 'B'): 11,
  (129, 'C'): 11,
  (129, 'D'): 11,
  (129, 'E'): 11,
  (129, 'F'): 11,
  (129, 'G'): 11,
  (129, 'H'): 11,
  (129, 'I'): 11,
  (129, 'J'): 11,
  (129, 'K'): 11,
  (129, 'L'): 11,
  (129, 'M'): 11,
  (129, 'N'): 11,
  (129, 'O'): 11,
  (129, 'P'): 11,
  (129, 'Q'): 11,
  (129, 'R'): 11,
  (129, 'S'): 11,
  (129, 'T'): 11,
  (129, 'U'): 11,
  (129, 'V'): 11,
  (129, 'W'): 11,
  (129, 'X'): 11,
  (129, 'Y'): 11,
  (129, 'Z'): 11,
  (129, '_'): 11,
  (129, 'a'): 11,
  (129, 'b'): 11,
  (129, 'c'): 11,
  (129, 'd'): 11,
  (129, 'e'): 11,
  (129, 'f'): 11,
  (129, 'g'): 11,
  (129, 'h'): 11,
  (129, 'i'): 11,
  (129, 'j'): 11,
  (129, 'k'): 11,
  (129, 'l'): 11,
  (129, 'm'): 11,
  (129, 'n'): 11,
  (129, 'o'): 130,
  (129, 'p'): 11,
  (129, 'q'): 11,
  (129, 'r'): 11,
  (129, 's'): 11,
  (129, 't'): 11,
  (129, 'u'): 11,
  (129, 'v'): 11,
  (129, 'w'): 11,
  (129, 'x'): 11,
  (129, 'y'): 11,
  (129, 'z'): 11,
  (130, '0'): 11,
  (130, '1'): 11,
  (130, '2'): 11,
  (130, '3'): 11,
  (130, '4'): 11,
  (130, '5'): 11,
  (130, '6'): 11,
  (130, '7'): 11,
  (130, '8'): 11,
  (130, '9'): 11,
  (130, 'A'): 11,
  (130, 'B'): 11,
  (130, 'C'): 11,
  (130, 'D'): 11,
  (130, 'E'): 11,
  (130, 'F'): 11,
  (130, 'G'): 11,
  (130, 'H'): 11,
  (130, 'I'): 11,
  (130, 'J'): 11,
  (130, 'K'): 11,
  (130, 'L'): 11,
  (130, 'M'): 11,
  (130, 'N'): 11,
  (130, 'O'): 11,
  (130, 'P'): 11,
  (130, 'Q'): 11,
  (130, 'R'): 11,
  (130, 'S'): 11,
  (130, 'T'): 11,
  (130, 'U'): 11,
  (130, 'V'): 11,
  (130, 'W'): 11,
  (130, 'X'): 11,
  (130, 'Y'): 11,
  (130, 'Z'): 11,
  (130, '_'): 11,
  (130, 'a'): 11,
  (130, 'b'): 11,
  (130, 'c'): 11,
  (130, 'd'): 11,
  (130, 'e'): 11,
  (130, 'f'): 11,
  (130, 'g'): 11,
  (130, 'h'): 11,
  (130, 'i'): 11,
  (130, 'j'): 11,
  (130, 'k'): 11,
  (130, 'l'): 11,
  (130, 'm'): 11,
  (130, 'n'): 11,
  (130, 'o'): 11,
  (130, 'p'): 11,
  (130, 'q'): 11,
  (130, 'r'): 11,
  (130, 's'): 11,
  (130, 't'): 11,
  (130, 'u'): 131,
  (130, 'v'): 11,
  (130, 'w'): 11,
  (130, 'x'): 11,
  (130, 'y'): 11,
  (130, 'z'): 11,
  (131, '0'): 11,
  (131, '1'): 11,
  (131, '2'): 11,
  (131, '3'): 11,
  (131, '4'): 11,
  (131, '5'): 11,
  (131, '6'): 11,
  (131, '7'): 11,
  (131, '8'): 11,
  (131, '9'): 11,
  (131, 'A'): 11,
  (131, 'B'): 11,
  (131, 'C'): 11,
  (131, 'D'): 11,
  (131, 'E'): 11,
  (131, 'F'): 11,
  (131, 'G'): 11,
  (131, 'H'): 11,
  (131, 'I'): 11,
  (131, 'J'): 11,
  (131, 'K'): 11,
  (131, 'L'): 11,
  (131, 'M'): 11,
  (131, 'N'): 11,
  (131, 'O'): 11,
  (131, 'P'): 11,
  (131, 'Q'): 11,
  (131, 'R'): 11,
  (131, 'S'): 11,
  (131, 'T'): 11,
  (131, 'U'): 11,
  (131, 'V'): 11,
  (131, 'W'): 11,
  (131, 'X'): 11,
  (131, 'Y'): 11,
  (131, 'Z'): 11,
  (131, '_'): 11,
  (131, 'a'): 11,
  (131, 'b'): 11,
  (131, 'c'): 11,
  (131, 'd'): 11,
  (131, 'e'): 11,
  (131, 'f'): 11,
  (131, 'g'): 11,
  (131, 'h'): 11,
  (131, 'i'): 11,
  (131, 'j'): 11,
  (131, 'k'): 11,
  (131, 'l'): 11,
  (131, 'm'): 11,
  (131, 'n'): 11,
  (131, 'o'): 11,
  (131, 'p'): 11,
  (131, 'q'): 11,
  (131, 'r'): 11,
  (131, 's'): 132,
  (131, 't'): 11,
  (131, 'u'): 11,
  (131, 'v'): 11,
  (131, 'w'): 11,
  (131, 'x'): 11,
  (131, 'y'): 11,
  (131, 'z'): 11,
  (132, '0'): 11,
  (132, '1'): 11,
  (132, '2'): 11,
  (132, '3'): 11,
  (132, '4'): 11,
  (132, '5'): 11,
  (132, '6'): 11,
  (132, '7'): 11,
  (132, '8'): 11,
  (132, '9'): 11,
  (132, 'A'): 11,
  (132, 'B'): 11,
  (132, 'C'): 11,
  (132, 'D'): 11,
  (132, 'E'): 11,
  (132, 'F'): 11,
  (132, 'G'): 11,
  (132, 'H'): 11,
  (132, 'I'): 11,
  (132, 'J'): 11,
  (132, 'K'): 11,
  (132, 'L'): 11,
  (132, 'M'): 11,
  (132, 'N'): 11,
  (132, 'O'): 11,
  (132, 'P'): 11,
  (132, 'Q'): 11,
  (132, 'R'): 11,
  (132, 'S'): 11,
  (132, 'T'): 11,
  (132, 'U'): 11,
  (132, 'V'): 11,
  (132, 'W'): 11,
  (132, 'X'): 11,
  (132, 'Y'): 11,
  (132, 'Z'): 11,
  (132, '_'): 11,
  (132, 'a'): 11,
  (132, 'b'): 11,
  (132, 'c'): 11,
  (132, 'd'): 11,
  (132, 'e'): 11,
  (132, 'f'): 11,
  (132, 'g'): 11,
  (132, 'h'): 11,
  (132, 'i'): 11,
  (132, 'j'): 11,
  (132, 'k'): 11,
  (132, 'l'): 11,
  (132, 'm'): 11,
  (132, 'n'): 11,
  (132, 'o'): 11,
  (132, 'p'): 11,
  (132, 'q'): 11,
  (132, 'r'): 11,
  (132, 's'): 11,
  (132, 't'): 11,
  (132, 'u'): 11,
  (132, 'v'): 11,
  (132, 'w'): 11,
  (132, 'x'): 11,
  (132, 'y'): 11,
  (132, 'z'): 11,
  (134, '='): 136,
  (137, '<'): 141,
  (139, '='): 140,
  (143, '0'): 144,
  (143, '1'): 144,
  (143, '2'): 144,
  (143, '3'): 144,
  (143, '4'): 144,
  (143, '5'): 144,
  (143, '6'): 144,
  (143, '7'): 144,
  (143, '8'): 144,
  (143, '9'): 144,
  (144, '0'): 144,
  (144, '1'): 144,
  (144, '2'): 144,
  (144, '3'): 144,
  (144, '4'): 144,
  (144, '5'): 144,
  (144, '6'): 144,
  (144, '7'): 144,
  (144, '8'): 144,
  (144, '9'): 144},
 set([1,
      2,
      3,
      4,
      5,
      6,
      8,
      9,
      10,
      11,
      12,
      13,
      14,
      16,
      17,
      18,
      19,
      20,
      21,
      22,
      23,
      24,
      25,
      26,
      27,
      28,
      29,
      30,
      31,
      32,
      33,
      34,
      35,
      36,
      37,
      38,
      39,
      40,
      41,
      42,
      43,
      44,
      45,
      46,
      47,
      48,
      49,
      50,
      51,
      52,
      53,
      54,
      55,
      56,
      57,
      58,
      59,
      60,
      61,
      62,
      63,
      64,
      65,
      66,
      67,
      68,
      69,
      70,
      71,
      72,
      73,
      74,
      75,
      76,
      77,
      78,
      79,
      80,
      81,
      82,
      83,
      84,
      85,
      86,
      87,
      88,
      90,
      93,
      95,
      96,
      97,
      98,
      100,
      101,
      102,
      103,
      104,
      105,
      106,
      107,
      108,
      110,
      111,
      113,
      114,
      115,
      116,
      117,
      118,
      119,
      120,
      121,
      122,
      123,
      124,
      125,
      126,
      127,
      128,
      129,
      130,
      131,
      132,
      133,
      134,
      135,
      136,
      138,
      139,
      140,
      141,
      142,
      144]),
 set([1,
      2,
      3,
      4,
      5,
      6,
      8,
      9,
      10,
      11,
      12,
      13,
      14,
      16,
      17,
      18,
      19,
      20,
      21,
      22,
      23,
      24,
      25,
      26,
      27,
      28,
      29,
      30,
      31,
      32,
      33,
      34,
      35,
      36,
      37,
      38,
      39,
      40,
      41,
      42,
      43,
      44,
      45,
      46,
      47,
      48,
      49,
      50,
      51,
      52,
      53,
      54,
      55,
      56,
      57,
      58,
      59,
      60,
      61,
      62,
      63,
      64,
      65,
      66,
      67,
      68,
      69,
      70,
      71,
      72,
      73,
      74,
      75,
      76,
      77,
      78,
      79,
      80,
      81,
      82,
      83,
      84,
      85,
      86,
      87,
      88,
      90,
      93,
      95,
      96,
      97,
      98,
      100,
      101,
      102,
      103,
      104,
      105,
      106,
      107,
      108,
      110,
      111,
      113,
      114,
      115,
      116,
      117,
      118,
      119,
      120,
      121,
      122,
      123,
      124,
      125,
      126,
      127,
      128,
      129,
      130,
      131,
      132,
      133,
      134,
      135,
      136,
      138,
      139,
      140,
      141,
      142,
      144]),
 ['0, 0, 0, start|, 0, start|, 0, 0, 0, 0, 0, start|, 0, 0, 0, 0, 0, 0, start|, 0, start|, 0, 0, start|, 0, 0, 0, 0, 0, 0, start|, 0, 0, 0, start|, 0, start|, start|, 0, 0, start|, 0, start|, start|, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0',
  'IGNORE',
  '(',
  'ATOM',
  'NUMBER',
  'NUMBER',
  'ATOM',
  '1, 1, 1, 1',
  'VAR',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  '|',
  'ATOM',
  '0, start|, 0, final*, start*, 0, 1, final*, 0, final|, start|, 0, 1, final*, start*, 0, final*, 0, 1, final|, start|, 0, final*, start*, 0, final*',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  '[',
  '{',
  'ATOM',
  '.',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'IGNORE',
  ')',
  'ATOM',
  'ATOM',
  ']',
  'ATOM',
  'ATOM',
  '}',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  '2',
  'ATOM',
  '2',
  '2',
  'ATOM',
  '2',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  '2',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'final*, start*, 2, final*, 0, start|, 0, 0, final*, start*, final*, 0, final*, start*, 0, final*, 0, final|, start|, 0, 1, final*, start*, final*, 0, final*, start*, 0, final*, 0, 1, final|, start|, 0, final*, start*, final*, 0, 1, final*, 0, start|, 0, final*, start*, final*, start*, 0, final*, 0, final*, final|, final*, 0, start|, 0, final*, start*, final*, start*, 0, final*, 0, final*, 1, final|, final*, 0, final|, start|, 0, 1, final*, start*, final*, start*, 0, final*, 0, final*, 0, 1, final|, start|, 0, final*, start*, final*, start*, 0, final*, 0',
  'ATOM',
  'ATOM',
  '0, final*, 1, 0, 1, 0, start|',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  '2',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  'ATOM',
  '1, 0',
  'NUMBER']), {'IGNORE': None})
basic_rules = [Rule('query', [['toplevel_op_expr', '.', 'EOF']]), Rule('fact', [['toplevel_op_expr', '.']]), Rule('complexterm', [['ATOM', '(', 'toplevel_op_expr', ')'], ['{', '}'], ['{', 'toplevel_op_expr', '}'], ['expr']]), Rule('expr', [['VAR'], ['NUMBER'], ['+', 'NUMBER'], ['-', 'NUMBER'], ['ATOM'], ['(', 'toplevel_op_expr', ')'], ['listexpr']]), Rule('listexpr', [['[', 'listbody', ']']]), Rule('listbody', [['toplevel_op_expr', '|', 'toplevel_op_expr'], ['toplevel_op_expr']])]
# generated code between this line and its other occurence
 
if __name__ == '__main__':
    f = py.path.local(__file__)
    oldcontent = f.read()
    s = "# GENERATED CODE BETWEEN THIS LINE AND ITS OTHER OCCURENCE\n".lower()
    pre, gen, after = oldcontent.split(s)

    lexer, parser_fact, parser_query, basic_rules = make_all()
    newcontent = ("%s%s\nparser_fact = %r\nparser_query = %r\n%s\n"
                  "basic_rules = %r\n%s%s") % (
            pre, s, parser_fact, parser_query, lexer.get_dummy_repr(),
            basic_rules, s, after)
    print newcontent
    f.write(newcontent)



