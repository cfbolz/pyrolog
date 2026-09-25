import pytest

from prolog.interpreter import parsing, term, error
from prolog.interpreter.test.tool import assert_true


def test_query_entry_point_preserves_parenthesized_argument():
    result = parsing.parse_query_term('f((a,b)).')
    assert result.argument_count() == 1
    assert result.argument_at(0).name() == ','


def test_query_entry_point_enforces_functor_adjacency():
    with pytest.raises(error.CatchableError):
        parsing.parse_query_term('f (a).')


def test_query_variables_and_default_operators():
    result, variables = parsing.get_query_and_vars('X = f(X, _, _), Y is 1+2*3.')
    first = result.argument_at(0)
    compound = first.argument_at(1)
    assert first.argument_at(0) is variables['X']
    assert compound.argument_at(0) is variables['X']
    assert compound.argument_at(1) is not compound.argument_at(2)
    assert set(variables) == set(['X', 'Y'])
    assert result.argument_at(1).argument_at(0) is variables['Y']


def test_read_uses_new_parser(tmpdir):
    path = tmpdir.join('terms.pl')
    path.write('f((a,b)). f (a).')
    assert_true("open('%s',read,S), read(S,T), functor(T,f,1), "
                "catch(read(S,_),error(syntax_error(_)),Caught=yes), "
                "Caught==yes,close(S)." % path)
