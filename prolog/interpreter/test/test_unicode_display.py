# coding: utf-8
import pytest
from prolog.interpreter.parsing import get_engine, parse_query_term
from prolog.interpreter.term import Callable
from prolog.builtin.formatting import TermFormatter
from prolog.interpreter.completion import PrologCompleter
from prolog.interpreter.test.test_highlighting import highlighted
from prolog.interpreter.test.tool import assert_true


@pytest.mark.parametrize('name', ['é', '变量', '😀', 'É', 'é', "l'été", 'a\\b',
                                   'a\x00b', 'a\nb', "'quoted'", 'é space'])
def test_quoted_atom_roundtrip(name):
    formatter = TermFormatter(get_engine(''), quoted=True)
    rendered = formatter.format(Callable.build(name))
    assert parse_query_term(rendered + '.').name() == name
    assert '\x00' not in rendered


def test_unicode_highlighting():
    assert highlighted('É = 变量(X́), _变量 = "😀".') == [
        ('É', 'VARIABLE'), ('X́', 'VARIABLE'), ('_变量', 'VARIABLE'),
        ('"😀"', 'STRING')]


def test_unicode_completion():
    engine = get_engine('éclair. école. 变量.')
    completer = PrologCompleter(engine)
    result = completer.complete('true, éc', len('true, éc'))
    assert result.start == len('true, ')
    assert sorted(result.candidates) == ['éclair', 'école']
    assert completer.complete('变', len('变')).candidates == ['变量']
    assert completer.complete('Éc', len('Éc')).candidates == []
    engine.runstring(':- module(模块,[谓词/0]). 谓词.')
    result = completer.complete('模块:谓', len('模块:谓'))
    assert result.start == len('模块:')
    assert result.candidates == ['谓词']


def test_read_unicode_terms_with_layout_and_quotes(tmpdir):
    path = tmpdir.join('terms.pl')
    path.write("% 😀 comment\n词('é space. % text', \"😀\").\n"
               "/* € */ 'it\\'s'.\n'\\x0\\'.", mode='wb')
    assert_true("open('%s',read,S), read(S,词('é space. %% text',[128512])), "
                "read(S,'it\\'s'), read(S,A), atom_codes(A,[0]), "
                "read(S,end_of_file), close(S)." % path)
