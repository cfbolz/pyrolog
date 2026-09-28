import pytest

from prolog.interpreter.continuation import Engine
from prolog.interpreter.test.tool import assert_true, collect_all


def test_consult_mode_declaration(tmpdir):
    source = tmpdir.join('modes.pl')
    source.write(':- mode(identity(+, ?, -)).\n'
                 'identity(X, Y, X) :- var(Y).\n')
    engine = Engine(load_system=True)
    assert_true("consult('%s'), identity(a, Y, Z), var(Y), Z == a."
                % source, engine)


def test_mode_succeeds_once_without_binding_argument():
    engine = Engine(load_system=True)
    assert len(collect_all(engine, 'mode(X), var(X).')) == 1


@pytest.mark.parametrize('declaration', [
    ':- dynamic(item/1).',
    ':- dynamic item/1.',
    ':- dynamic item/1, other/1.',
])
@pytest.mark.parametrize('module', ['user', 'declared'])
def test_consult_dynamic_declaration(tmpdir, declaration, module):
    source = tmpdir.join('dynamic.pl')
    header = '' if module == 'user' else ':- module(declared, []).\n'
    source.write(header + declaration + '\n'
                 'item(original).\n'
                 'update :- retract(item(original)), '
                 'asserta(item(first)), assertz(item(last)).\n')
    engine = Engine(load_system=True)
    assert_true("consult('%s'), %s:update." % (source, module), engine)
    answers = collect_all(engine, '%s:item(X).' % module)
    assert [answer['X'].name() for answer in answers] == ['first', 'last']


def test_dynamic_succeeds_once_without_binding_argument():
    engine = Engine(load_system=True)
    assert len(collect_all(engine, 'dynamic(X), var(X).')) == 1
