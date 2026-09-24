import pytest

from prolog.interpreter.parsing import get_engine
from prolog.interpreter.parsing import get_query_and_vars
from prolog.interpreter.error import UncaughtError
from prolog.interpreter.signature import Signature

@pytest.fixture(autouse=True)
def plain_diagnostics(monkeypatch):
    monkeypatch.setenv('NO_COLOR', '1')


def get_uncaught_error(query, e):
    if isinstance(query, str):
        (query, _) = get_query_and_vars(query)
    return pytest.raises(UncaughtError, e.run_query_in_current, query).value


def test_errstr():
    e = get_engine("""
        f(X) :- drumandbass(X).
    """)
    error = get_uncaught_error("f(X).", e)
    assert error.get_errstr(e) == "Undefined procedure: drumandbass/1"

def test_errstr_user():
    e = get_engine("""
        f(X) :- throw(foo).
    """)
    error = get_uncaught_error("f(X).", e)
    assert error.get_errstr(e) == "Unhandled exception: foo"


def test_resource_error_display():
    e = get_engine('')
    error = get_uncaught_error('throw(error(resource_error(memory))).', e)
    assert error.get_errstr(e) == 'Resource error: memory'


@pytest.mark.parametrize('query, expected', [
    ('L = [1|L], length(L, N).',
     "Type error: 'list' expected, found '@(_G0, [_G0=[1|_G0]])'"),
    ('X = f(X), throw(X).', "Unhandled exception: @(_G0, [_G0=f(_G0)])"),
    ('X = f(X), throw(error(domain_error(example, X))).',
     "Domain error: 'example' expected, found '@(_G0, [_G0=f(_G0)])'"),
])
def test_cyclic_error_display(query, expected):
    e = get_engine('', load_system=True)
    err = get_uncaught_error(query, e)
    assert err.get_errstr(e) == expected
    assert err.get_errstr(e) == expected


def test_deep_finite_error_display_stays_bounded():
    from prolog.interpreter import term
    from prolog.interpreter.error import TermedError
    obj = term.Callable.build('a')
    for i in range(3000):
        obj = term.Callable.build('f', [obj])
    message = TermedError(obj).get_errstr(get_engine(''))
    assert message == 'Unhandled exception: ' + 'f(' * 20 + '...' + ')' * 20

def test_exception_knows_rule():
    e = get_engine("""
        f(1).
        f(X) :- drumandbass(X).
    """)
    (t, vs) = get_query_and_vars("f(X), X = 2.")

    m = e.modulewrapper
    sig = t.argument_at(0).signature()
    rule = m.user_module.lookup(sig).rulechain.next
    error = get_uncaught_error(t, e)
    assert error.rule is rule

def test_exception_knows_rule_toplevel():
    # toplevel rule
    e = get_engine("")
    m = e.modulewrapper
    error = get_uncaught_error("drumandbass(X).", e)
    assert error.rule is m.current_module._toplevel_rule

def test_exception_knows_rule_change_back_to_earlier_rule():
    e = get_engine("""
        g(a).
        f(X) :- g(X), drumandbass(X).
    """)
    (t, vs) = get_query_and_vars("f(X).")

    m = e.modulewrapper
    sig = t.signature()
    rule = m.user_module.lookup(sig).rulechain

    error = get_uncaught_error(t, e)
    assert error.rule is rule

def test_exception_knows_builtin_signature():
    e = get_engine("""
        f(X, Y) :- atom_length(X, Y).
    """)
    error = get_uncaught_error("f(1, Y).", e)
    assert error.sig_context == Signature.getsignature("atom_length", 2)

def test_traceback():
    e = get_engine("""
        h(y).
        g(a).
        g(_) :- throw(foo).
        f(X, Y) :- g(X), h(Y).
    """)
    error = get_uncaught_error("f(1, Y).", e)
    sig_g = Signature.getsignature("g", 1)
    sig_f = Signature.getsignature("f", 2)
    m = e.modulewrapper
    rule_f = m.user_module.lookup(sig_f).rulechain
    rule_g = m.user_module.lookup(sig_g).rulechain.next
    tb = error.traceback
    assert tb.rule is rule_f
    assert tb.next.rule is rule_g
    assert tb.next.next is None

@pytest.mark.xfail
def test_traceback_in_if():
    e = get_engine("""
        h(y).
        g(a).
        g(_) :- throw(foo).
        f(X, Y) :- (g(X) -> X = 1 ; X = 2), h(Y).
    """)
    error = get_uncaught_error("f(1, Y).", e)
    sig_g = Signature.getsignature("g", 1)
    sig_f = Signature.getsignature("f", 2)
    m = e.modulewrapper
    rule_f = m.user_module.lookup(sig_f).rulechain
    rule_g = m.user_module.lookup(sig_g).rulechain.next
    tb = error.traceback
    assert tb.rule is rule_f
    assert tb.next.rule is rule_g

def test_traceback_print():
    e = get_engine("""
h(y).
g(a).
g(_) :- throw(foo).
f(X, Y) :-
    g(X),
    h(Y).
:- assert((h :- g(b), true)).
    """)
    error = get_uncaught_error("f(1, Y).", e)
    s = error.format_traceback(e)
    assert s == """\
Traceback (most recent call last):
  File "<unknown>" lines 5-7 in user:f/2
    f(X, Y) :-
        g(X),
        h(Y).
  File "<unknown>" line 4 in user:g/1
    g(_) :- throw(foo).
Unhandled exception: foo"""

    error = get_uncaught_error("h.", e)
    s = error.format_traceback(e)
    assert s == """\
Traceback (most recent call last):
  File "<unknown>" in user:h/0
  File "<unknown>" line 4 in user:g/1
    g(_) :- throw(foo).
Unhandled exception: foo"""

def test_traceback_print_builtin():
    e = get_engine("""
h(y).
g(a).
g(_) :- _ is _.
f(X, Y) :-
    g(X),
    h(Y).
:- assert((h :- g(b), true)).
    """)
    error = get_uncaught_error("f(1, Y).", e)
    s = error.format_traceback(e)
    assert s == """\
Traceback (most recent call last):
  File "<unknown>" lines 5-7 in user:f/2
    f(X, Y) :-
        g(X),
        h(Y).
  File "<unknown>" line 4 in user:g/1
    g(_) :- _ is _.
is/2: arguments not sufficiently instantiated"""

def test_traceback_print_no_context():
    e = get_engine("")
    error = get_uncaught_error("f(1, Y).", e)
    s = error.format_traceback(e)
    assert s == """\
Traceback (most recent call last):
  File "<unknown>" in user:<user toplevel>/0
Undefined procedure: f/2"""


def test_colored_traceback_keeps_plain_text_and_links_files(monkeypatch):
    import re
    from rpyrepl.color import MAGENTA, BOLD_MAGENTA, RESET, filelink
    e = get_engine('')
    filename = '/tmp/source file.pl'
    e.runstring('f :-\n g, true.\ng :- _ is _.\n', file_name=filename)
    exc = get_uncaught_error('f.', e)
    plain = exc.format_traceback(e, query_source='f.')
    monkeypatch.delenv('NO_COLOR')
    monkeypatch.setenv('FORCE_COLOR', '1')
    colored = exc.format_traceback(e, query_source='f.')
    assert MAGENTA + '<stdin>' + RESET in colored
    assert '\n    f.\n' in colored
    assert MAGENTA + filelink(filename) + RESET in colored
    assert MAGENTA + 'user:f/0' + RESET in colored
    assert MAGENTA + 'lines 1-2 ' + RESET in colored
    assert BOLD_MAGENTA + 'is/2: ' + RESET in colored
    assert MAGENTA + 'arguments not sufficiently instantiated' + RESET in colored
    unlinked = colored.replace(filelink(filename), filename)
    assert re.sub('\x1b\\[[0-9;]*m', '', unlinked) == plain
    assert '\x1b' not in plain


def test_colored_traceback_omits_links_for_unknown_source(monkeypatch):
    monkeypatch.delenv('NO_COLOR')
    monkeypatch.setenv('FORCE_COLOR', '1')
    e = get_engine('f :- throw(oops).')
    colored = get_uncaught_error('f.', e).format_traceback(e)
    assert '<unknown>' in colored
    assert '\x1b]8;' not in colored


def test_traceback_without_frames():
    from prolog.interpreter.term import Callable
    e = get_engine('')
    exc = UncaughtError(Callable.build('oops'))
    assert exc.format_traceback(e) == 'Traceback (most recent call last):\nUnhandled exception: oops'
    assert exc.format_traceback(e, query_source='throw(oops).') == (
        'Traceback (most recent call last):\n'
        '  File "<stdin>" in toplevel\n'
        '    throw(oops).\nUnhandled exception: oops')


def test_traceback_query_source_replaces_dummy_frame():
    e = get_engine('')
    exc = get_uncaught_error('missing.', e)
    before = exc.format_traceback(e)
    result = exc.format_traceback(e, query_source='true,\n  missing.\n')
    assert result == ('Traceback (most recent call last):\n'
                      '  File "<stdin>" in toplevel\n'
                      '    true,\n      missing.\n'
                      'Undefined procedure: missing/0')
    # Formatting must not modify the captured frames or shared module rule.
    assert exc.format_traceback(e) == before
    assert e.modulewrapper.current_module._toplevel_rule.source is None


def test_traceback_query_source_preserves_rule_frames():
    e = get_engine('f :- throw(oops).')
    exc = get_uncaught_error('f.', e)
    plain = exc.format_traceback(e)
    result = exc.format_traceback(e, query_source='f.')
    header, rest = plain.split('\n', 1)
    assert result == header + '\n  File "<stdin>" in toplevel\n    f.\n' + rest


def test_repl_passes_full_input_to_traceback(monkeypatch):
    from prolog.interpreter import translatedmain
    e = get_engine('')
    lines = iter(['true. missing.\n', 'halt.\n'])
    output = []
    monkeypatch.setattr(translatedmain.rpyrepl, 'make_reader', lambda **kw: None)
    monkeypatch.setattr(translatedmain, 'readline', lambda: next(lines))
    monkeypatch.setattr(translatedmain, 'printmessage', output.append)
    translatedmain.repl(e)
    result = ''.join(output)
    assert '  File "<stdin>" in toplevel\n    true. missing.\n' in result
    assert '<user toplevel>' not in result
