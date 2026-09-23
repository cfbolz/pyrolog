# coding: utf-8
import pytest
from prolog.interpreter.parsing import get_engine, parse_query_term
from prolog.interpreter.term import Callable
from prolog.builtin.formatting import TermFormatter
from prolog.interpreter.completion import PrologCompleter
from prolog.interpreter.test.test_highlighting import highlighted
from prolog.interpreter.test.tool import assert_true
from prolog.interpreter.replpolicy import PrologInputPolicy


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


@pytest.mark.parametrize('text, more', [
    ("X = 'é\\'😀'.", False),
    ("X = 'é\\'😀", True),
    ("X = '\\x0\\'.", False),
    ("X = 'it''s'.", False),
    ('X = 0\'😀.', False),
])
def test_unicode_query_termination(text, more):
    assert PrologInputPolicy().more_lines(text) == more


@pytest.mark.parametrize('bad', ['\x01', '\x00', '1.0e+', 'a(\x01)'])
def test_read_lexical_error_preserves_next_term(tmpdir, bad):
    path = tmpdir.join('invalid-term.pl')
    path.write(bad + '. good.\n', mode='wb')
    assert_true("open('%s',read,S), "
                "catch(read(S,_),error(syntax_error(E)),true), "
                "nonvar(E), read(S,good), read(S,end_of_file), close(S)." % path)


@pytest.mark.parametrize('source, expected', [
    ("'first. second'. good.", "'first. second'"),
    ('"first. second". good.', '[102,105,114,115,116,46,32,115,101,99,111,110,100]'),
    ('/* first. second */ value. good.', 'value'),
    ('% first. second\nvalue. good.', 'value'),
])
def test_read_waits_for_complete_quoted_tokens_and_comments(tmpdir, source, expected):
    path = tmpdir.join('incomplete-prefix.pl')
    path.write(source, mode='wb')
    assert_true("open('%s',read,S),read(S,%s),read(S,good),close(S)." %
                (path, expected))


def test_read_lexical_error_does_not_wait_for_eof():
    from prolog.builtin.streams import read_till_next_dot
    from prolog.interpreter import error
    from prolog.interpreter.stream import PrologInputStream

    class OpenPipe(object):
        # Reading beyond this prefix would block on a real open pipe.
        available = '\x01. '

        def try_to_find_file_descriptor(self):
            return 99

        def read(self, count):
            assert self.available, 'read/2 requested input after the bad term'
            result = self.available[:count]
            self.available = self.available[count:]
            return result

    stream = PrologInputStream(OpenPipe())
    with pytest.raises(error.CatchableError):
        read_till_next_dot(stream)
    assert stream.read(1) == ' '
