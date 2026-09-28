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
