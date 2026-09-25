import pytest

from prolog.interpreter.lexer import UnicodeLexer
from prolog.interpreter.newparser import OperatorTable, Parser, ParseError
from prolog.interpreter import term


def operator_table(definitions):
    table = OperatorTable()
    for name, precedence, form in definitions:
        table.add(name, precedence, form)
    return table


def infix_table():
    return operator_table([
        ('+', 500, 'yfx'), ('-', 500, 'yfx'), ('*', 400, 'yfx'),
        ('^', 200, 'xfy'), ('=', 700, 'xfx'), (',', 1000, 'xfy'),
    ])


def parse(source, operators=None):
    if operators is None:
        operators = infix_table()
    return Parser(UnicodeLexer().tokenize(source), operators).parse()


def shape(value):
    if isinstance(value, term.Number):
        return value.num
    if isinstance(value, term.Atom):
        return value.name()
    return (value.name(),) + tuple(shape(value.argument_at(i))
                                  for i in range(value.argument_count()))


def test_operator_table():
    table = operator_table([('+', 500, 'yfx'), ('+', 200, 'fy'),
                            ('!', 400, 'xf')])
    assert table.infix_ops['+'].name == '+'
    assert table.infix_ops['+'].left_limit == 500
    assert table.infix_ops['+'].right_limit == 499
    assert table.prefix_ops['+'].kind == 'prefix'
    assert table.postfix_ops['!'].left_limit == 399
    table.add('+', 300, 'xfy')
    assert table.infix_ops['+'].right_limit == 300
    assert table.prefix_ops['+'].precedence == 200


@pytest.mark.parametrize('source, expected', [
    ('1+2*3.', ('+', 1, ('*', 2, 3))),
    ('1*2+3.', ('+', ('*', 1, 2), 3)),
    ('1-2-3.', ('-', ('-', 1, 2), 3)),
    ('1^2^3.', ('^', 1, ('^', 2, 3))),
    ('(1+2)*3.', ('*', ('+', 1, 2), 3)),
    ('1-(2-3).', ('-', 1, ('-', 2, 3))),
    ('(1=2)=3.', ('=', ('=', 1, 2), 3)),
    ('a+b*c.', ('+', 'a', ('*', 'b', 'c'))),
    ('f(1+2, 3*4).', ('f', ('+', 1, 2), ('*', 3, 4))),
    ('f((a,b), c).', ('f', (',', 'a', 'b'), 'c')),
    ('{a,b}.', ('{}', (',', 'a', 'b'))),
    ('[1+2,3|a+b].', ('.', ('+', 1, 2), ('.', 3, ('+', 'a', 'b')))),
])
def test_infix(source, expected):
    assert shape(parse(source)) == expected


@pytest.mark.parametrize('source', ['1=2=3.', '1+.', 'f(a,,b).',
                                   '[a|b,c].', '1 2.'])
def test_invalid_infix(source):
    with pytest.raises(ParseError):
        parse(source)


def test_precedence_clash_keeps_operator_token():
    with pytest.raises(ParseError) as exc:
        parse('1=2=3.')
    assert exc.value.tok.source == '='
    assert exc.value.tok.source_pos.i == 3


def test_operator_override():
    table = infix_table()
    table.add('+', 300, 'yfx')
    assert shape(parse('1+2*3.', table)) == ('*', ('+', 1, 2), 3)


def test_argument_maximum_precedence():
    table = operator_table([('then', 1100, 'xfy')])
    with pytest.raises(ParseError):
        parse('f(a then b).', table)
    assert shape(parse('f((a then b)).', table)) == ('f', ('then', 'a', 'b'))


def test_variables_shared_across_expressions():
    parser = Parser(UnicodeLexer().tokenize('f(X+Y, [Y*X]).'), infix_table())
    result = parser.parse()
    left = result.argument_at(0)
    right = result.argument_at(1).argument_at(0)
    assert left.argument_at(0) is right.argument_at(1)
    assert left.argument_at(1) is right.argument_at(0)
    assert left.argument_at(0) is parser.varname_to_var['X']


@pytest.mark.parametrize('source, definitions, expected', [
    ('~ 1.', [('~', 500, 'fx')], ('~', 1)),
    ('~ ~ 1.', [('~', 500, 'fy')], ('~', ('~', 1))),
    ('~ 1*2+3.', [('~', 450, 'fy')], ('+', ('~', ('*', 1, 2)), 3)),
    ('1+ ~ 2*3.', [('~', 450, 'fy')], ('+', 1, ('~', ('*', 2, 3)))),
    ('~ 1+2.', [('~', 500, 'fx')], ('+', ('~', 1), 2)),
    ('~ 1+2.', [('~', 500, 'fy')], ('~', ('+', 1, 2))),
    ('1 ! !.', [('!', 500, 'yf')], ('!', ('!', 1))),
    ('1 ! ? .', [('!', 400, 'xf'), ('?', 500, 'xf')], ('?', ('!', 1))),
    ('1+2 !.', [('!', 300, 'yf')], ('+', 1, ('!', 2))),
    ('1+2 !.', [('!', 600, 'yf')], ('!', ('+', 1, 2))),
    ('1 ! +2.', [('!', 300, 'yf')], ('+', ('!', 1), 2)),
    ('~ (~ 1).', [('~', 500, 'fx')], ('~', ('~', 1))),
    ('(1 !) !.', [('!', 500, 'xf')], ('!', ('!', 1))),
    ('f(~ a, [b !]).', [('~', 500, 'fy'), ('!', 500, 'yf')],
     ('f', ('~', 'a'), ('.', ('!', 'b'), '[]'))),
    ('~(a,b).', [('~', 500, 'fy')], ('~', 'a', 'b')),
    ('~ (a,b).', [('~', 500, 'fy')], ('~', (',', 'a', 'b'))),
    ('p a p p b.', [('p', 200, 'fy'), ('p', 500, 'yfx')],
     ('p', ('p', 'a'), ('p', 'b'))),
])
def test_prefix_postfix(source, definitions, expected):
    table = infix_table()
    for definition in definitions:
        table.add(*definition)
    assert shape(parse(source, table)) == expected


@pytest.mark.parametrize('prefix, postfix, expected', [
    ('fx', 'yf', ('!', ('~', 1))),
    ('fy', 'xf', ('~', ('!', 1))),
    ('fy', 'yf', ('~', ('!', 1))),
])
def test_equal_precedence_prefix_postfix(prefix, postfix, expected):
    table = operator_table([('~', 500, prefix), ('!', 500, postfix)])
    assert shape(parse('~ 1 !.', table)) == expected


@pytest.mark.parametrize('source, definitions', [
    ('~ ~ 1.', [('~', 500, 'fx')]),
    ('1 ! !.', [('!', 500, 'xf')]),
    ('~ 1 !.', [('~', 500, 'fx'), ('!', 500, 'xf')]),
    ('1 + ~ 2.', [('~', 500, 'fy')]),
    ('1 ~ 2.', [('~', 500, 'fy')]),
    ('1+2 !.', [('!', 500, 'xf')]),
])
def test_invalid_prefix_postfix(source, definitions):
    table = infix_table()
    for definition in definitions:
        table.add(*definition)
    with pytest.raises(ParseError):
        parse(source, table)
