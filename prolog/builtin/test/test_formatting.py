import pytest
from prolog.builtin import formatting
from prolog.interpreter.parsing import parse_query_term
from prolog.interpreter.continuation import Engine
from prolog.interpreter.term import Callable, BindingVar
from prolog.interpreter.test.tool import assert_true


@pytest.mark.parametrize('text, depth, expected', [
    ('f(a,b,c,d).', 2, 'f(a, b, c, d)'),
    ('f(g(a),g(b)).', 2, 'f(g(...), g(...))'),
    ('f(g(a),g(b)).', 3, 'f(g(a), g(b))'),
    ('[a,b,c,d].', 1, '[...|...]'),
    ('[a,b,c,d].', 2, '[a|...]'),
    ('[a,b,c,d].', 3, '[a, b|...]'),
    ('[a].', 1, '[...]'),
    ('[a].', 2, '[a]'),
    ('[f(a),f(b)].', 2, '[f(...)|...]'),
    ('[a,b|tail].', 0, '[a, b|tail]'),
    ('1+(2*3).', 2, '1+...*...'),
])
def test_depth_per_path(text, depth, expected):
    formatter = formatting.TermFormatter(Engine(), max_depth=depth)
    obj = parse_query_term(text)
    assert formatter.format(obj) == expected
    # Reusing a formatter must start a new path, not accumulate depth.
    assert formatter.format(obj) == expected


@pytest.mark.parametrize('query, expected', [
    ('X = f(X).', 'f(f(f(...)))'),
    ('X = [a|X].', '[a, a|...]'),
    ('X = 1+X.', '1+(1+(... + ...))'),
    ('X = (a,X).', '(a, a, ..., ...)'),
])
def test_bounded_cycles(query, expected):
    obj = assert_true(query)['X']
    formatter = formatting.TermFormatter(Engine(), max_depth=3)
    assert formatter.format(obj).replace(' ', '') == expected.replace(' ', '')


def test_bounded_cycle_without_operator_syntax():
    obj = assert_true('X = [a|X].')['X']
    formatter = formatting.TermFormatter(Engine(), max_depth=2, ignore_ops=True)
    assert formatter.format(obj) == '.(a, .(..., ...))'


def test_bounded_attribute_cycle():
    from prolog.interpreter.continuation import Heap
    var = Heap().new_attvar()
    var.add_attribute('m', var)
    formatter = formatting.TermFormatter(Engine(), max_depth=2)
    assert formatter.format(var) == 'put_attr(_G0, m, put_attr(_G0, m, ...))'


def test_write_term_bounded_cycle(capfd):
    assert_true('X = [a|X], write_term(X, [max_depth(3)]).')
    out, err = capfd.readouterr()
    assert out == '[a, a|...]'


def test_console_formats_cyclic_list():
    from prolog.interpreter.translatedmain import var_representation
    variables = assert_true('X = [a|X].')
    output = []
    var_representation(variables, Engine(), output.append, None)
    assert output == ['X = [' + ', '.join(['a'] * 19) + '|...]\n']

def test_list():
    f = formatting.TermFormatter(Engine(), quoted=False, ignore_ops=False)
    t = parse_query_term("[1, 2, 3, 4, 5 | X].")
    assert f.format(t) == "[1, 2, 3, 4, 5|_G0]"
    t = parse_query_term("[a, b, 'A$%%$$'|[]].")
    assert f.format(t) == "[a, b, A$%%$$]"
    t = parse_query_term("'.'(a, b, c).")
    assert f.format(t) == ".(a, b, c)"

    X = BindingVar()
    a = Callable.build('a')
    t = Callable.build(".", [a, X])
    X.binding = Callable.build(".", [a, Callable.build("[]")])
    assert f.format(t) == "[a, a]"



def test_op_formatting():
    f = formatting.TermFormatter(Engine(), quoted=False, ignore_ops=False)
    t = parse_query_term("'+'(1, 2).")
    assert f.format(t) == "1+2"
    t = parse_query_term("'+'(1, *(3, 2)).")
    assert f.format(t) == "1+3*2"
    t = parse_query_term("'*'(1, *(3, 2)).")
    assert f.format(t) == "1*(3*2)"

def test_atom_formatting():
    f = formatting.TermFormatter(Engine(), quoted=False, ignore_ops=False)
    t = parse_query_term("'abc def'.")
    assert f.format(t) == "abc def"
    f = formatting.TermFormatter(Engine(), quoted=True, ignore_ops=False)
    t = parse_query_term("'abc def'.")
    assert f.format(t) == "'abc def'"
    t = parse_query_term("abc.")
    assert f.format(t) == "abc"
