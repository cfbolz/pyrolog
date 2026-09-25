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
    ('1+(2*3).', 2, '1+ ... * ...'),
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
    from prolog.interpreter.answer import format_answer
    variables = assert_true('X = [a|X].')
    output = format_answer(variables, [], Engine()).splitlines(True)
    assert output == ['X = [a|X]\n']


@pytest.mark.parametrize('query, expected', [
    ('X = f(X,f(X)).', ['X = f(X, f(X))']),
    ('X = f(Y), Y = g(X).', ['X = f(g(X))', 'Y = g(X)']),
    ('X = f(X), Y = X.', ['X = f(X)', 'Y = X']),
    ('X = f(X,A), Y = g(A,X).', ['X = f(X, A)', 'Y = g(A, X)']),
    ('_C = f(_C), X = g(_C,_C).', ['X = g(_G0, _G0)', '_G0 = f(_G0)']),
    ('X = f(X), Y = g(Y).', ['X = f(X)', 'Y = g(Y)']),
    ('X = Y.', ['Y = X']),
    ('X = f(A), Y = g(A).', ['X = f(A)', 'Y = g(A)']),
    ("X = 'with space'(X).", ["X = 'with space'(X)"]),
])
def test_console_recursive_equations(query, expected):
    from prolog.interpreter.answer import format_answer
    variables = assert_true(query)
    output = format_answer(variables, [], Engine()).splitlines(True)
    assert output == [line + '\n' for line in expected]
    # Formatting is read-only and repeatable, including generated labels.
    repeated = format_answer(variables, [], Engine()).splitlines(True)
    assert repeated == output


def test_console_deep_term_still_truncates():
    from prolog.interpreter.answer import format_answer
    obj = Callable.build('a')
    for i in range(3000):
        obj = Callable.build('f', [obj])
    output = format_answer({'X': obj}, [], Engine()).splitlines(True)
    assert output == ['X = ' + 'f(' * 20 + '...' + ')' * 20 + '\n']


def test_answer_factorization_preserves_sharing():
    obj = Callable.build('a')
    for i in range(24):
        obj = Callable.build('f', [obj, obj])
    factorizer = formatting.CycleFactorizer()
    copied = factorizer.visit(obj)
    assert len(factorizer.finished) == 24
    for i in range(24):
        assert copied.argument_at(0) is copied.argument_at(1)
        copied = copied.argument_at(0)


@pytest.mark.parametrize('query, expected', [
    ('X = f(X).', '@(_G0, [_G0=f(_G0)])'),
    ('X = [a|X].', '@(_G0, [_G0=[a|_G0]])'),
    ('X = 1+X.', '@(_G0, [_G0=1+_G0])'),
    ('X = (a,X).', '@(_G0, [_G0=(a, _G0)])'),
    ('X = f(Y), Y = g(X).', '@(_G0, [_G0=f(g(_G0))])'),
    ('C = f(C), X = pair(C,C).', '@(pair(_G0, _G0), [_G0=f(_G0)])'),
    ('X = f(X,A).', '@(_G0, [_G0=f(_G0, _G1)])'),
])
def test_cycle_notation(query, expected):
    obj = assert_true(query)['X']
    formatter = formatting.TermFormatter(Engine())
    assert formatter.format(obj) == expected


@pytest.mark.parametrize('ignore_ops', [False, True])
def test_cycle_notation_can_be_reconstructed(ignore_ops):
    from prolog.interpreter.continuation import Heap
    from prolog.interpreter.helper import unwrap_list
    from prolog.builtin.unify import identical
    obj = assert_true("A = 'with space'(A), B = [a|B], X = pair(A,B,A).")['X']
    formatter = formatting.TermFormatter(Engine(), quoted=True, ignore_ops=ignore_ops)
    text = formatter.format(obj)
    display = parse_query_term(text + '.')
    assert display.name() == '@'
    heap = Heap()
    for equation in unwrap_list(display.argument_at(1)):
        equation.argument_at(0).unify(equation.argument_at(1), heap)
    assert identical(obj, display.argument_at(0))


def test_cycle_display_preserves_input_and_variable_names():
    variables = assert_true('X = f(X,A).')
    obj, free = variables['X'], variables['A']
    formatter = formatting.TermFormatter(Engine())
    assert formatter.format(free) == '_G0'
    assert formatter.format(obj) == '@(_G1, [_G1=f(_G1, _G0)])'
    assert free.getbinding() is None
    assert obj.argument_at(0).dereference(None) is obj
    assert formatter.format(parse_query_term('plain.')) == 'plain'


def test_acyclic_sharing_is_not_factorized():
    obj = assert_true('T = f(A), X = pair(T,T).')['X']
    assert formatting.TermFormatter(Engine()).format(obj) == 'pair(f(_G0), f(_G0))'


def test_write_cycle_options(capfd):
    from prolog.interpreter.test.tool import prolog_raises
    assert_true('X = [a|X], write(X).')
    out, err = capfd.readouterr()
    assert out == '@(_G0, [_G0=[a|_G0]])'
    assert_true('X = f(X), write_term(X, [cycles(true),max_depth(2)]).')
    out, err = capfd.readouterr()
    assert out == 'f(f(...))'
    prolog_raises('domain_error(cyclic_term, T)',
                  'X = f(X), write_term(X, [cycles(false)])')
    prolog_raises('domain_error(cyclic_term, T)',
                  'X = f(X), write_term(X, [cycles(false),max_depth(2)])')
    assert_true('write_term(f(a), [cycles(false)]).')
    out, err = capfd.readouterr()
    assert out == 'f(a)'


def test_unrestricted_attribute_cycle():
    from prolog.interpreter.continuation import Heap
    var = Heap().new_attvar()
    var.add_attribute('m', var)
    formatter = formatting.TermFormatter(Engine())
    assert formatter.format(var) == 'put_attr(_G0, m, _G0)'
    assert not formatter.active_attvars
    cyclic = assert_true('X = f(X).')['X']
    var.add_attribute('m', cyclic)
    assert formatter.format(var) == 'put_attr(_G0, m, @(_G1, [_G1=f(_G1)]))'

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


@pytest.mark.parametrize('bindings, options, obj, expected', [
    ('O=quoted(V),V=true', '[O]', "'Capital'", "'Capital'"),
    ('D=1', '[max_depth(D)]', 'f(a)', 'f(...)'),
    ('B=true,O=ignore_ops(B)', '[O]', '1+2', '+(1, 2)'),
])
def test_bound_write_options(capfd, bindings, options, obj, expected):
    assert_true('%s,write_term(%s,%s).' % (bindings, obj, options))
    assert capfd.readouterr()[0] == expected
