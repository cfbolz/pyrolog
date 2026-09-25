"""Public parsing entry points, using the handwritten UTF-8 term parser."""
from rpython.rlib.parsing.deterministic import LexerError
from prolog.interpreter.lexer import UnicodeLexer
from prolog.interpreter.termparser import Parser, OperatorTable, ParseError
from prolog.interpreter import error


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


def make_operator_table(operations):
    table = OperatorTable()
    for precedence, groups in operations:
        for form, names in groups:
            for name in names:
                table.add(name, precedence, form)
    return table


default_operator_table = make_operator_table(default_operations)

lexer = UnicodeLexer()


def _dummyfunc(arg, value, source, file_name, start, end):
    pass


def parse_file(s, operators=None, callback=_dummyfunc, arg=None, file_name=None):
    return parse_file_with_vars(s, operators, callback, arg, file_name)[0]


def parse_file_with_vars(s, operators=None, callback=_dummyfunc, arg=None, file_name=None):
    if file_name is None:
        file_name = '<unknown>'
    if operators is None:
        operators = default_operator_table
    eof = None
    parse_error = None
    try:
        tokens = lexer.tokenize(s, eof=True)
        eof = tokens.pop()
        return _parse_file(tokens, eof, operators, callback, arg, s, file_name)
    except ParseError as exc:
        parse_error = exc
        token = exc.tok
        if token is None:
            assert eof is not None
            token = eof
        pos = token.source_pos
        lines = s.split('\n')
        message = ('  File %s, line %s\n%s\n%s^\nParseError: %s' %
                   (file_name, pos.lineno + 1, lines[pos.lineno],
                    ' ' * pos.columnno, exc.msg))
        lineno = pos.lineno
    except LexerError as exc:
        message = exc.nice_error_message(file_name)
        lineno = exc.source_pos.lineno
    raise error.PrologParseError(file_name, lineno, message, parse_error)


def _parse_file(tokens, eof, operators, callback, arg, source, file_name):
    terms = []
    variables = {}
    line = []
    for token in tokens:
        line.append(token)
        if token.name == '.':
            parser = Parser(line, operators)
            value = parser.parse()
            variables = parser.varname_to_var
            next_operators = callback(arg, value, source, file_name,
                                      line[0].source_pos, token.source_pos)
            # Directives can modify operators or switch the current module.
            if next_operators is not None:
                operators = next_operators
            terms.append(value)
            line = []
    if line:
        # Diagnose the final unfinished term too, using the true source EOF.
        Parser(line + [eof], operators).parse()
        assert False, 'a term without a full stop cannot parse successfully'
    return terms, variables


def parse_query(s, operators=None):
    return parse_query_term(s, operators)


def parse_query_term(s, operators=None):
    return get_query_and_vars(s, operators)[0]


def get_query_and_vars(s, operators=None):
    if operators is None:
        operators = default_operator_table
    parser = Parser(lexer.tokenize(s, eof=True), operators)
    try:
        query = parser.parse()
    except ParseError as exc:
        reason = 'float_overflow' if exc.msg == 'float overflow' else exc.msg
        raise error.throw_syntax_error(reason, exc)
    return query, parser.varname_to_var


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
