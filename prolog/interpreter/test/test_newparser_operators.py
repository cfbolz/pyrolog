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


def test_high_precedence_prefix_name_in_predicate_indicator():
    table = operator_table([('block', 1050, 'fx'), ('/', 400, 'yfx')])
    assert shape(parse('f(block/1).', table)) == ('f', ('/', 'block', 1))


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


def ambiguous_table():
    return operator_table([('@', 500, 'yfx'), ('@', 400, 'yf'),
                           ('#', 600, 'yfx'), ('!', 600, 'yf'),
                           ('~', 200, 'fy')])


@pytest.mark.parametrize('source, expected', [
    ('1 @ 2.', ('@', 1, 2)),
    ('1 @ .', ('@', 1)),
    ('(1 @).', ('@', 1)),
    ('1 @ # 2.', ('#', ('@', 1), 2)),
    ('1 @ ! .', ('!', ('@', 1))),
    ('1 @ @ 2.', ('@', ('@', 1), 2)),
    ('1 @ ~ 2.', ('@', 1, ('~', 2))),
    ('f(1 @, 2).', ('f', ('@', 1), 2)),
    ('[1 @ | []].', ('.', ('@', 1), '[]')),
    ('{1 @}.', ('{}', ('@', 1))),
])
def test_infix_postfix_reinterpretation(source, expected):
    assert shape(parse(source, ambiguous_table())) == expected


@pytest.mark.parametrize('form, precedence', [('xfx', 500), ('yfx', 400)])
def test_reinterpretation_requires_greater_left_limit(form, precedence):
    table = ambiguous_table()
    table.add('#', precedence, form)
    with pytest.raises(ParseError):
        parse('1 @ # 2.', table)


def test_reinterpretation_can_choose_incoming_postfix():
    table = ambiguous_table()
    table.add('!', 400, 'yfx')  # left limit too small for reinterpretation
    assert shape(parse('1 @ ! .', table)) == ('!', ('@', 1))


def test_reinterpreted_postfix_still_checks_operand():
    table = ambiguous_table()
    table.add('+', 450, 'yfx')
    with pytest.raises(ParseError):
        parse('1+2 @ .', table)


def test_reinterpreted_postfix_still_checks_expression_limit():
    table = ambiguous_table()
    table.add('@', 1100, 'yf')
    with pytest.raises(ParseError):
        parse('f(1 @).', table)


@pytest.mark.parametrize('source, expected', [
    ('~ .', '~'),
    ('~ ~ .', ('~', '~')),
    ('~ = a.', ('=', '~', 'a')),
    ('f(~, p, +).', ('f', '~', 'p', '+')),
    ('[~,p].', ('.', '~', ('.', 'p', '[]'))),
    ("'~'.", '~'),
    ("'~'(a,b).", ('~', 'a', 'b')),
    ("f(',', '+').", ('f', ',', '+')),
    ('a + p(b,c).', ('+', 'a', ('p', 'b', 'c'))),
    ('a + @(b,c).', ('+', 'a', ('@', 'b', 'c'))),
])
def test_operator_names_as_atoms_and_functors(source, expected):
    table = infix_table()
    table.add('~', 500, 'fy')
    table.add('p', 1100, 'fy')
    table.add('@', 500, 'yfx')
    table.add('@', 400, 'yf')
    assert shape(parse(source, table)) == expected


@pytest.mark.parametrize('source', ["a '+' b.", "'~' a."])
def test_quoted_names_do_not_act_as_operators(source):
    table = infix_table()
    table.add('~', 500, 'fy')
    with pytest.raises(ParseError):
        parse(source, table)


def test_unicode_operator_name_and_error_position():
    name = '\xe2\x89\xa4'  # U+2264
    table = operator_table([(name, 700, 'xfx')])
    assert shape(parse('a' + name + 'b.', table)) == (name, 'a', 'b')
    with pytest.raises(ParseError) as exc:
        parse('a' + name + 'b' + name + 'c.', table)
    assert exc.value.tok.source == name
    assert exc.value.tok.source_pos.i == 5
    assert exc.value.tok.source_pos.columnno == 3


def test_long_operator_chain():
    result = parse('^'.join(['1'] * 2000) + '.')
    for unused in range(1999):
        assert result.name() == '^'
        assert result.argument_at(0).num == 1
        result = result.argument_at(1)
    assert result.num == 1


@pytest.mark.parametrize('literal', ['-1', '-0xff', "-0'a"])
def test_negative_integer_literal(literal):
    value = parse(literal + '.', OperatorTable())
    assert isinstance(value, term.Number)
    assert value.num == {'-1': -1, '-0xff': -255, "-0'a": -97}[literal]


def test_negative_integer_boundaries():
    import sys
    value = parse(str(-sys.maxint - 1) + '.', OperatorTable())
    assert isinstance(value, term.Number)
    assert value.num == -sys.maxint - 1
    value = parse(str(-(2 ** 100)) + '.', OperatorTable())
    assert isinstance(value, term.BigInt)
    assert value.value.str() == str(-(2 ** 100))


def test_negative_float_literal():
    import math
    value = parse('-1.5.', OperatorTable())
    assert isinstance(value, term.Float)
    assert value.floatval == -1.5
    zero = parse('-0.0.', OperatorTable())
    assert math.copysign(1.0, zero.floatval) == -1.0


@pytest.mark.parametrize('source, expected', [
    ('- 1.', ('-', 1)), ('-(1).', ('-', 1)), ('- (1).', ('-', 1)),
    ('+1.', ('+', 1)), ('- -1.', ('-', -1)),
    ('-1^2.', ('^', -1, 2)), ('1 - -2.', ('-', 1, -2)),
])
def test_numeric_sign_vs_prefix_operator(source, expected):
    table = infix_table()
    table.add('-', 200, 'fy')
    table.add('+', 200, 'fy')
    assert shape(parse(source, table)) == expected
