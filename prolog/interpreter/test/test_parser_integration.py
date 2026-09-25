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


def test_quoted_comma_atom_roundtrip():
    from prolog.builtin.formatting import TermFormatter
    from prolog.interpreter.continuation import Engine
    rendered = TermFormatter(Engine(), quoted=True).format(term.Callable.build(','))
    assert rendered == "','"
    assert parsing.parse_query_term(rendered + '.').name() == ','


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


def test_file_returns_terms_with_separate_variable_scopes():
    first, second = parsing.parse_file('f(X,X). g(X).')
    assert first.name() == 'f'
    assert first.argument_at(0) is first.argument_at(1)
    assert first.argument_at(0) is not second.argument_at(0)


def test_engine_parse_uses_new_parser():
    from prolog.interpreter.continuation import Engine
    terms, variables = Engine().parse('f((a,b), X).')
    assert terms[0].argument_count() == 2
    assert terms[0].argument_at(1) is variables['X']
    with pytest.raises(error.PrologParseError):
        Engine().parse('f (a).')


def test_consult_runs_directives_between_terms():
    engine = parsing.get_engine('first. :- assert(second). third.')
    assert_true('first, second, third.', engine)


def test_rule_source_spans_with_utf8():
    from prolog.interpreter.signature import Signature
    source = '% comment\n\xc3\xa9(X) :-\n    X = a.\n\nnext.\n'
    engine = parsing.get_engine(source)
    rule = engine.modulewrapper.current_module.lookup(Signature.getsignature('\xc3\xa9', 1)).rulechain
    assert rule.source == '\xc3\xa9(X) :-\n    X = a.'
    assert rule.line_range == [1, 3]


def test_file_error_keeps_location():
    with pytest.raises(error.PrologParseError) as exc:
        parsing.parse_file('good.\nbad (x).', file_name='example.pl')
    assert exc.value.file_name == 'example.pl'
    assert exc.value.line_number == 1
    assert 'bad (x).' in exc.value.message
    assert '[example.pl:2:5]' in exc.value.message
    assert 'whitespace before this parenthesis' in exc.value.message
    assert 'functor name here' in exc.value.message
