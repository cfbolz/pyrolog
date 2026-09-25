import pytest

from prolog.interpreter.lexer import UnicodeLexer
from prolog.interpreter.termparser import Parser, OperatorTable
from prolog.interpreter.syntaxerror import SyntaxError
from prolog.interpreter.term import Atom, Number, BigInt, Float, Var


def parse(source):
    tokens = UnicodeLexer().tokenize(source)
    # Start with no operators; commas still separate compound arguments.
    return Parser(tokens, OperatorTable()).parse()


def test_atom():
    result = parse("hello.")
    assert isinstance(result, Atom)
    assert result.name() == "hello"


@pytest.mark.parametrize("source, expected", [
    ("'hello world'.", "hello world"),
    ("''.", ""),
    ("'X'.", "X"),
    ("'can''t'.", "can't"),
    (r"'can\'t'.", "can't"),
    (r"'a\nb'.", "a\nb"),
    (r"'a\\b'.", "a\\b"),
    (r"'\u00e9\U0001f600'.", "\xc3\xa9\xf0\x9f\x98\x80"),
    ("'\xc3\xa9'.", "\xc3\xa9"),
])
def test_quoted_atom(source, expected):
    result = parse(source)
    assert isinstance(result, Atom)
    assert result.name() == expected


def test_quoted_functor():
    result = parse("'can''t'('hello world', X).")
    assert result.name() == "can't"
    assert result.argument_count() == 2
    assert isinstance(result.argument_at(0), Atom)
    assert result.argument_at(0).name() == "hello world"
    assert isinstance(result.argument_at(1), Var)


@pytest.mark.parametrize("source", [r"'\q'.", r"'\uD800'.", r"'\U00110000'."])
def test_invalid_quoted_escape(source):
    with pytest.raises(SyntaxError) as exc:
        parse(source)
    assert exc.value.primary.start.i == 1
    assert exc.value.primary.end.i == len(source) - 2


def test_integer():
    result = parse("42.")
    assert isinstance(result, Number)
    assert result.num == 42


@pytest.mark.parametrize("source, expected", [
    ("0.", 0), ("009.", 9), ("0xff.", 255),
    ("0o17.", 15), ("0b101.", 5), ("0xAbCd.", 43981),
    ("0'a.", 97), ("0'''.", 39), ("0'\xc3\xa9.", 233),
    (r"0'\n.", 10), (r"0'\U0001f600.", 0x1f600),
    (r"0'\x41\.", 65), (r"0'\101\.", 65),
])
def test_integer_literals(source, expected):
    result = parse(source)
    assert isinstance(result, Number)
    assert result.num == expected


@pytest.mark.parametrize("literal", [
    str(2 ** 100), "0x1" + "0" * 25,
    "0b1" + "0" * 100, "0o2" + "0" * 33,
])
def test_large_integer(literal):
    result = parse(literal + ".")
    assert isinstance(result, BigInt)
    assert result.value.str() == str(2 ** 100)


@pytest.mark.parametrize("literal, expected", [
    ("0.0", 0.0), ("12.5", 12.5), ("1.25e3", 1250.0),
    ("1.25E-2", 0.0125), ("1.0e+2", 100.0),
])
def test_float_literal(literal, expected):
    result = parse(literal + ".")
    assert isinstance(result, Float)
    assert result.floatval == expected


@pytest.mark.parametrize("literal", [
    "1.0e999", "1" + "0" * 400 + ".0",
    r"0'\q", r"0'\uD800", r"0'\U00110000",
])
def test_invalid_numeric_literal(literal):
    with pytest.raises(SyntaxError):
        parse(literal + ".")


def test_nested_compound():
    result = parse("f(a, g(42), c).")
    assert result.name() == "f"
    assert result.argument_count() == 3
    first = result.argument_at(0)
    assert isinstance(first, Atom)
    assert first.name() == "a"
    nested = result.argument_at(1)
    assert nested.name() == "g"
    assert nested.argument_count() == 1
    number = nested.argument_at(0)
    assert isinstance(number, Number)
    assert number.num == 42
    last = result.argument_at(2)
    assert isinstance(last, Atom)
    assert last.name() == "c"


def test_parentheses():
    result = parse("(f((42))).")
    assert result.name() == "f"
    assert result.argument_count() == 1
    assert isinstance(result.argument_at(0), Number)
    assert result.argument_at(0).num == 42


def test_named_variables():
    parser = Parser(UnicodeLexer().tokenize("f(X, g(X, Y), Y)."), OperatorTable())
    result = parser.parse()
    x = result.argument_at(0)
    y = result.argument_at(2)
    assert isinstance(x, Var)
    assert isinstance(y, Var)
    assert x is not y
    nested = result.argument_at(1)
    assert nested.argument_at(0) is x
    assert nested.argument_at(1) is y
    assert set(parser.varname_to_var) == set(["X", "Y"])
    assert parser.varname_to_var["X"] is x
    assert parser.varname_to_var["Y"] is y


def test_anonymous_variables():
    parser = Parser(UnicodeLexer().tokenize("f(_, _, _X, _X)."), OperatorTable())
    result = parser.parse()
    first = result.argument_at(0)
    second = result.argument_at(1)
    named = result.argument_at(2)
    assert isinstance(first, Var)
    assert isinstance(second, Var)
    assert isinstance(named, Var)
    assert first is not second
    assert first is not named
    assert second is not named
    assert result.argument_at(3) is named
    assert set(parser.varname_to_var) == set(["_X"])
    assert parser.varname_to_var["_X"] is named


def test_variable_scope():
    first_parser = Parser(UnicodeLexer().tokenize("X."), OperatorTable())
    second_parser = Parser(UnicodeLexer().tokenize("X."), OperatorTable())
    first = first_parser.parse()
    second = second_parser.parse()
    assert isinstance(first, Var)
    assert isinstance(second, Var)
    assert first is not second
    assert first_parser.varname_to_var["X"] is first
    assert second_parser.varname_to_var["X"] is second


@pytest.mark.parametrize("source", ["", "f(a", "f().", "f(a,).", "(a.",
                                   "a. b.", "a + b."])
def test_invalid_syntax(source):
    with pytest.raises(SyntaxError):
        parse(source)


def list_cell(value):
    assert value.name() == "."
    assert value.argument_count() == 2
    return value.argument_at(0), value.argument_at(1)


@pytest.mark.parametrize("literal, expected", [
    ('""', []),
    ('"ab"', [97, 98]),
    ('"a""b"', [97, 34, 98]),
    (r'"a\"b"', [97, 34, 98]),
    (r'"\n\\"', [10, 92]),
    ('"can\'\'t"', [99, 97, 110, 39, 39, 116]),
    ('"\xc3\xa9\xf0\x9f\x98\x80"', [233, 0x1f600]),
    (r'"\u00e9\U0001f600"', [233, 0x1f600]),
    (r'"\u0000"', [0]),
])
def test_double_quoted_codes(literal, expected):
    result = parse(literal + ".")
    for code in expected:
        head, result = list_cell(result)
        assert isinstance(head, Number)
        assert head.num == code
    assert isinstance(result, Atom)
    assert result.name() == "[]"


def test_double_quoted_codes_in_compound():
    result = parse('f("a", "").')
    assert result.name() == "f"
    assert result.argument_count() == 2
    head, tail = list_cell(result.argument_at(0))
    assert isinstance(head, Number)
    assert head.num == 97
    assert tail.name() == "[]"
    assert isinstance(result.argument_at(1), Atom)
    assert result.argument_at(1).name() == "[]"


@pytest.mark.parametrize("literal", [r'"\q"', r'"\uD800"', r'"\U00110000"'])
def test_invalid_double_quoted_escape(literal):
    with pytest.raises(SyntaxError) as exc:
        parse(literal + ".")
    assert exc.value.primary.start.i == 1
    assert exc.value.primary.end.i == len(literal) - 1


@pytest.mark.parametrize("source", ["[].", "[ ]."])
def test_empty_list(source):
    result = parse(source)
    assert isinstance(result, Atom)
    assert result.name() == "[]"


@pytest.mark.parametrize("source", ["[a, b].", "[a, b | []]."])
def test_proper_list(source):
    first, rest = list_cell(parse(source))
    second, tail = list_cell(rest)
    assert isinstance(first, Atom)
    assert first.name() == "a"
    assert isinstance(second, Atom)
    assert second.name() == "b"
    assert isinstance(tail, Atom)
    assert tail.name() == "[]"


def test_improper_list():
    head, tail = list_cell(parse("[a | b]."))
    assert isinstance(head, Atom)
    assert head.name() == "a"
    assert isinstance(tail, Atom)
    assert tail.name() == "b"


def test_list_variable_sharing():
    parser = Parser(UnicodeLexer().tokenize("f(X, [X, a | T], T)."), OperatorTable())
    result = parser.parse()
    first, rest = list_cell(result.argument_at(1))
    second, tail = list_cell(rest)
    assert isinstance(first, Var)
    assert first is result.argument_at(0)
    assert first is parser.varname_to_var["X"]
    assert second.name() == "a"
    assert isinstance(tail, Var)
    assert tail is result.argument_at(2)
    assert tail is parser.varname_to_var["T"]
    assert first is not tail


def test_nested_list():
    nested, rest = list_cell(parse("[[a], f(b, c)]."))
    head, inner_tail = list_cell(nested)
    assert head.name() == "a"
    assert isinstance(inner_tail, Atom)
    assert inner_tail.name() == "[]"
    compound, tail = list_cell(rest)
    assert compound.name() == "f"
    assert compound.argument_count() == 2
    assert compound.argument_at(0).name() == "b"
    assert compound.argument_at(1).name() == "c"
    assert isinstance(tail, Atom)
    assert tail.name() == "[]"


@pytest.mark.parametrize("source", [
    "[a,].", "[,a].", "[|T].", "[a|].", "[a|b,c].", "[a|b|c].",
    "[a b].", "[a.", "[a",
])
def test_invalid_list(source):
    with pytest.raises(SyntaxError):
        parse(source)


@pytest.mark.parametrize("source", ["{}.", "{ }."])
def test_empty_braces(source):
    result = parse(source)
    assert isinstance(result, Atom)
    assert result.name() == "{}"


def test_braces():
    result = parse("{a}.")
    assert result.name() == "{}"
    assert result.argument_count() == 1
    assert isinstance(result.argument_at(0), Atom)
    assert result.argument_at(0).name() == "a"


def test_nested_braces():
    result = parse("{{f(a, b)}}.")
    assert result.name() == "{}"
    assert result.argument_count() == 1
    inner = result.argument_at(0)
    assert inner.name() == "{}"
    assert inner.argument_count() == 1
    compound = inner.argument_at(0)
    assert compound.name() == "f"
    assert compound.argument_count() == 2
    assert compound.argument_at(0).name() == "a"
    assert compound.argument_at(1).name() == "b"


def test_braces_variable_sharing():
    parser = Parser(UnicodeLexer().tokenize("f(X, {X})."), OperatorTable())
    result = parser.parse()
    braces = result.argument_at(1)
    assert braces.name() == "{}"
    assert braces.argument_count() == 1
    assert isinstance(result.argument_at(0), Var)
    assert braces.argument_at(0) is result.argument_at(0)
    assert braces.argument_at(0) is parser.varname_to_var["X"]


@pytest.mark.parametrize("source", ["{a", "{a.", "{a).", "{a b}.", "{a, b}."])
def test_invalid_braces_without_operators(source):
    with pytest.raises(SyntaxError):
        parse(source)


@pytest.mark.parametrize("functor, expected", [
    ("f", "f"), ("'hello world'", "hello world"),
    ("'can''t'", "can't"), (r"'\u00e9'", "\xc3\xa9"),
    ("'\xc3\xa9'", "\xc3\xa9"), ("\xc3\xa9", "\xc3\xa9"),
])
def test_compound_parenthesis_adjacency(functor, expected):
    result = parse(functor + "( a ).")
    assert result.name() == expected
    assert result.argument_count() == 1
    assert result.argument_at(0).name() == "a"


@pytest.mark.parametrize("functor", ["f", "'hello world'", "'\xc3\xa9'"])
@pytest.mark.parametrize("gap", [" ", "\t", "\n", "/*comment*/", "%comment\n"])
def test_compound_parenthesis_requires_adjacency(functor, gap):
    with pytest.raises(SyntaxError):
        parse(functor + gap + "(a).")
