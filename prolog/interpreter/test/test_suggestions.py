import pytest
from rpython.rlib import rutf8
from prolog.interpreter import suggestions
from prolog.interpreter.error import UncaughtError
from prolog.interpreter.parsing import get_engine
from prolog.interpreter.signature import Signature
from prolog.interpreter.test.tool import assert_true


def codes(text):
    return list(rutf8.Utf8StringIterator(text.encode('utf-8')))


@pytest.mark.parametrize('a,b,expected', [
    (u'cat', u'sat', 2), (u'cat', u'ca', 2), (u'cat', u'caT', 1),
    (u'lenght', u'length', 4), (u'', u'cat', 6),
    (u'caf\xe9', u'caf\xe8', 2), (u'\xc4', u'\xe4', 1),
    (u'\u754c', u'', 2), (u'same', u'same', 0),
])
def test_distance_and_cutoff(a, b, expected):
    for budget in range(8):
        for left, right in [(a, b), (b, a)]:
            result = suggestions.levenshtein_distance(codes(left), codes(right), budget)
            if expected <= budget:
                assert result == expected
            else:
                assert result > budget


def matches(engine, name, arity):
    result = suggestions.predicate_suggestions(
        engine, engine.modulewrapper.current_module,
        Signature.getsignature(name, arity))
    return [[s.string() for s in group] for group in result]


def test_spelling_arity_and_builtin_aliases():
    e = get_engine('length(_, _, _).', load_system=True)
    assert matches(e, 'lenght', 2) == [[], ['length/2']]
    assert matches(e, 'length', 1) == [['length/2', 'length/3'], []]
    assert matches(e, 'atom_chrs', 2) == [[], ['atom_chars/2']]
    assert matches(e, 'assert', 2)[0] == ['assert/1']
    assert matches(e, 'ab', 0) == [[], []]
    assert matches(e, 'zzzzzzzz', 0) == [[], []]


def test_ties_are_sorted_capped_and_replaced_by_a_better_match():
    e = get_engine('fooe. food. fooc. foob. fooa.')
    assert matches(e, 'foox', 0) == [[], ['fooa/0', 'foob/0', 'fooc/0']]
    e.runstring("'fooX'.")
    assert matches(e, 'foox', 0) == [[], ['fooX/0']]


@pytest.mark.parametrize('requested, expected', [
    (0, [1, 2, 3]),
    (4, [3, 2, 1]),
    (6, [3, 9, 2]),  # Equal distances prefer the lower arity.
    (10, [9, 3, 2]),  # Select nearby arities before truncating to three.
])
def test_arity_suggestions_prefer_nearby_arities(requested, expected):
    e = get_engine('')
    for arity in [9, 3, 2, 1]:
        e.runstring('predicate(' + ','.join(['a'] * arity) + ').')
    assert matches(e, 'predicate', requested) == [
        ['predicate/%d' % arity for arity in expected], []]


def test_unicode_and_length_limit():
    e = get_engine(u"'caf\xe9'.".encode('utf-8'))
    assert matches(e, u'caf\xe8'.encode('utf-8'), 0) == [[], [u'caf\xe9/0'.encode('utf-8')]]
    name = 'a' * 41
    e.runstring(name + '(a).')
    assert matches(e, name, 0) == [[name + '/1'], []]
    assert matches(e, 'a' * 40 + 'b', 1) == [[], []]


def test_candidate_limit_does_not_hide_arity_hints():
    e = get_engine('candidate(a).')
    e.runstring(' '.join('candidate%d.' % i for i in range(750)))
    assert matches(e, 'candidate', 0) == [['candidate/1'], []]


def render(engine, query):
    goal = engine.parse(query)[0][0]
    exc = pytest.raises(UncaughtError, engine.run_query_in_current, goal).value
    return exc, exc.format_traceback(engine)


def test_lookup_scope_survives_unwinding_and_includes_imports(monkeypatch):
    monkeypatch.setenv('NO_COLOR', '1')
    e = get_engine('fooz.')
    e.runstring(':- module(exporter, [foob/0]). foob. fooc.')
    exporter = e.modulewrapper.current_module
    e.runstring(':- module(other, [go/0]). fooa. go :- foox.')
    other = e.modulewrapper.current_module
    other.use_module(exporter)
    e.switch_module('user')
    for query in ['other:go.', 'other:foox.', 'call(other:foox).']:
        exc, text = render(e, query)
        assert exc.lookup_module is other
        assert text.endswith('help: similarly named predicates are available: fooa/0, foob/0')
        assert 'fooc/0' not in text
        assert 'fooz/0' not in text


def test_qualified_lookup_includes_runtime_fallbacks(monkeypatch):
    monkeypatch.setenv('NO_COLOR', '1')
    e = get_engine('', load_system=True)
    e.switch_module('other')
    e.switch_module('user')
    assert render(e, 'other:lenght([], N).')[1].endswith('length/2')
    assert render(e, 'other:atom_chrs(a, X).')[1].endswith('atom_chars/2')
    # A missing module is not a misspelled predicate in the current module.
    assert 'help:' not in render(e, 'unknown:lenght([], N).')[1]


def test_only_rendering_an_uncaught_lookup_error_computes_suggestions(monkeypatch):
    e = get_engine('foobar :- assertz(executed).')
    calls = []
    original = suggestions.predicate_suggestions
    def record(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(suggestions, 'predicate_suggestions', record)
    assert_true('catch(foobra, error(existence_error(procedure, foobra/0)), true).', e)
    assert calls == []
    goal = e.parse('foobra.')[0][0]
    exc = pytest.raises(UncaughtError, e.run_query_in_current, goal).value
    assert calls == []
    assert exc.get_errstr(e) == 'Undefined procedure: foobra/0'
    assert calls == []
    assert 'help: a similarly named predicate is available: foobar/0' in exc.format_traceback(e)
    assert len(calls) == 1
    assert e.modulewrapper.current_module.lookup(Signature.getsignature('executed', 0)) is None
    render(e, 'throw(error(existence_error(procedure, foobra/0))).')
    render(e, "consult('/nonexistent/foobra.pl').")
    assert len(calls) == 1


def test_quoted_names_wrong_arities_and_empty_predicates(monkeypatch):
    monkeypatch.setenv('NO_COLOR', '1')
    e = get_engine("'hello world'(a). 'hello world'(a, b). empty_name.")
    text = render(e, "'hello world'.")[1]
    assert text.endswith("help: predicates with this name exist at other arities: 'hello world'/1, 'hello world'/2")
    assert render(e, 'empty_name(X).')[1].endswith(
        'help: a predicate with this name exists at another arity: empty_name/0')
    assert_true('retract(empty_name).', e)
    assert matches(e, 'empty_nam', 0) == [[], ['empty_name/0']]


def test_suggestions_work_with_tracing(monkeypatch):
    from prolog.interpreter.trace import TraceObserver
    e = get_engine('foobar.')
    e.debugger.observer = TraceObserver()
    e.debugger.enable()
    assert 'foobar/0' in render(e, 'foobra.')[1]


@pytest.mark.parametrize('tracing', [False, True])
def test_recovery_error_suggestions_only_when_uncaught(monkeypatch, tracing):
    from prolog.interpreter.trace import TraceObserver
    monkeypatch.setenv('NO_COLOR', '1')
    e = get_engine('foobar. unrelated.')
    if tracing:
        e.debugger.observer = TraceObserver()
        e.debugger.enable()
    calls = []
    original = suggestions.predicate_suggestions
    def record(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(suggestions, 'predicate_suggestions', record)
    assert_true('catch(catch(foobra, _, unrelate), '
                'error(existence_error(procedure, unrelate/0)), true).', e)
    assert calls == []
    goal = e.parse('catch(foobra, _, unrelate).')[0][0]
    exc = pytest.raises(UncaughtError, e.run_query_in_current, goal).value
    assert calls == []
    assert exc.get_errstr(e) == 'Undefined procedure: unrelate/0'
    assert exc.format_traceback(e).endswith(
        'help: a similarly named predicate is available: unrelated/0')
    assert len(calls) == 1
