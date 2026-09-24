import pytest
from prolog.interpreter.test.tool import assert_true, prolog_raises


@pytest.mark.parametrize('option', ['type', 'encoding', 'alias', 'buffer'])
@pytest.mark.parametrize('value, expected', [
    ('_', 'instantiation_error'),
    ('42', 'type_error(atom,42)'),
    ('f(a)', 'type_error(atom,f(a))'),
    ('[a]', 'type_error(atom,[a])'),
])
def test_stream_option_value_validation(tmpdir, option, value, expected):
    path = tmpdir.join('untouched')
    path.write('original')
    prolog_raises(expected, "open('%s',write,_,[%s(%s)])" % (path, option, value))
    assert path.read() == 'original'


@pytest.mark.parametrize('option', ['foo', '[]', 'type(text,binary)', '42', '1.5'])
def test_malformed_stream_option(tmpdir, option):
    path = tmpdir.join('not-created')
    prolog_raises('domain_error(stream_option,%s)' % option,
                  "open('%s',write,_,[%s])" % (path, option))
    assert not path.exists()


def test_unbound_stream_option(tmpdir):
    prolog_raises('instantiation_error', "open('%s',write,_,[_])" % tmpdir.join('unused'))


def test_unknown_unary_stream_options_are_ignored(tmpdir):
    assert_true("open('%s',write,S,[foo(a),foo(_),foo(42)]),close(S)." %
                tmpdir.join('unknown'))


def test_duplicate_stream_options_still_validate_each_value(tmpdir):
    path = tmpdir.join('unused')
    prolog_raises('instantiation_error',
                  "open('%s',write,_,[type(_),type(text)])" % path)
    prolog_raises('type_error(atom,42)',
                  "open('%s',write,_,[type(42),type(text)])" % path)
    assert not path.exists()


def test_duplicate_stream_options_use_last_value(tmpdir):
    path = tmpdir.join('binary')
    assert_true("open('%s',write,S,[type(invalid),type(binary),"
                "encoding(invalid),encoding(octet)]),put_byte(S,255),close(S)." % path)
    assert path.read(mode='rb') == '\xff'
