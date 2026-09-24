import pytest

from prolog.interpreter.lexer import UnicodeLexer
from prolog.interpreter.newparser import Parser, ParseError
from prolog.interpreter.term import Atom, Number, Var


def parse(source):
    tokens = UnicodeLexer().tokenize(source)
    # Start with no operators; commas still separate compound arguments.
    return Parser(tokens, []).parse()


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
    with pytest.raises(ParseError) as exc:
        parse(source)
    assert exc.value.tok.source == source[:-1]


def test_integer():
    result = parse("42.")
    assert isinstance(result, Number)
    assert result.num == 42


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
    parser = Parser(UnicodeLexer().tokenize("f(X, g(X, Y), Y)."), [])
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
    parser = Parser(UnicodeLexer().tokenize("f(_, _, _X, _X)."), [])
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
    first_parser = Parser(UnicodeLexer().tokenize("X."), [])
    second_parser = Parser(UnicodeLexer().tokenize("X."), [])
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
    with pytest.raises(ParseError):
        parse(source)
