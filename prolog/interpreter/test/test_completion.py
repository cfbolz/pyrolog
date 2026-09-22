import pytest
from prolog.interpreter.completion import PrologCompleter
from prolog.interpreter.parsing import get_engine
from prolog.interpreter.signature import Signature


def matches(e, text):
    return sorted(PrologCompleter(e).complete(text, len(text)).candidates)


def test_local_imported_system_and_builtin_names():
    e = get_engine('apple. apple(X). apricot.', load_system=True)
    assert matches(e, 'ap') == ['append', 'apple', 'apricot']
    assert 'atom_codes' in matches(e, 'atom_')
    e.modulewrapper.current_module.lookup(Signature.getsignature('apparition', 0))
    assert 'apparition' not in matches(e, 'ap')
    e.runstring(':- module(other, [apex/0]). apex. private.')
    other = e.modulewrapper.current_module
    e.switch_module('user')
    e.modulewrapper.current_module.use_module(other)
    assert 'apex' in matches(e, 'ap')
    assert matches(e, 'user:ap') == ['apex', 'apple', 'apricot']
    assert matches(e, 'other:pri') == ['private']
    assert matches(e, 'unknown:pri') == []


@pytest.mark.parametrize('text', ['Ap', '_ap', "'ap", '"ap', '% ap',
                                  '/* ap', "f('ap')", '', ' ', '123ap',
                                  '/* user:', '% user:', "'user:", '"user:',
                                  'user: % */'])
def test_no_variables_quotes_comments_or_empty_completion(text):
    e = get_engine('apple.')
    assert matches(e, text) == []


def test_candidates_follow_database_changes_and_module_switches():
    e = get_engine('apple.')
    assert matches(e, 'ap') == ['apple']
    e.runstring('apricot.')
    assert matches(e, 'ap') == ['apple', 'apricot']
    e.switch_module('other')
    assert matches(e, 'ap') == []


def test_replacement_starts_after_module_qualifier():
    e = get_engine('apple.')
    result = PrologCompleter(e).complete('true, user:ap(X)', 13)
    assert result.start == 11
    assert result.candidates == ['apple']


def test_module_names_and_qualified_candidates():
    e = get_engine('tools.')
    e.runstring(':- module(tools, [frobnicate/0]). frobnicate. private.')
    e.switch_module('user')
    assert matches(e, 'too') == ['tools', 'tools:']
    assert matches(e, 'tools:fro') == ['frobnicate']
    assert matches(e, 'tools:pri') == ['private']
    assert matches(e, 'tools:too') == []
    assert matches(e, 'tools:atom_cod') == []
    assert matches(e, 'unknown:fro') == []


def test_empty_qualified_stem_lists_predicates():
    e = get_engine('', load_system=True)
    result = PrologCompleter(e).complete('list:', 5)
    assert result.start == 5
    assert 'append' in result.candidates
    assert 'reverse' in result.candidates
    assert 'atom_codes' not in result.candidates
    assert 'true' not in result.candidates
    assert 'term_expand' not in result.candidates
    assert matches(e, 'list:t') == []
    assert 'list:' not in result.candidates
    assert matches(e, 'missing:') == []


@pytest.mark.parametrize('before, after', [
    ('', ' '), (' ', ''), (' ', ' '), ('\n', '\t'),
    (' /* qualifier */ ', ' /* predicate */ '),
    ('/* qualifier */', '/* predicate */'),
    (' % qualifier\n', ' % predicate\n'),
])
def test_qualified_completion_ignores_layout(before, after):
    e = get_engine('', load_system=True)
    prefix = 'list' + before + ':' + after
    assert matches(e, prefix + 't') == []
    assert matches(e, prefix + 'rev') == ['reverse']
    assert matches(e, prefix) == matches(e, 'list:')
    result = PrologCompleter(e).complete(prefix + 'rev(X)', len(prefix) + 3)
    assert result.start == len(prefix)
    assert result.candidates == ['reverse']
    assert matches(e, 'missing' + before + ':' + after + 'rev') == []
