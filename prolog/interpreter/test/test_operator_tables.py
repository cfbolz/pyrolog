from prolog.interpreter.module import Module


def test_module_operator_tables_are_independent():
    first, second = Module('first'), Module('second')
    first.operators.add('+', 350, 'xfy')
    assert first.operators.infix_ops['+'].precedence == 350
    assert second.operators.infix_ops['+'].precedence == 500
    assert first.operators.prefix_ops['+'].precedence == 500


def test_remove_operator_by_kind():
    table = Module('first').operators
    table.remove('+', 'xfy')
    assert '+' not in table.infix_ops
    assert '+' in table.prefix_ops
    table.remove('+', 'yfx')  # Removing an absent declaration succeeds.
    table.remove('+', 'fy')
    assert '+' not in table.prefix_ops


def test_operator_enumeration():
    table = Module('first').operators
    table.add('testop', 400, 'xf')
    found = [(op.name, op.precedence, op.form) for op in table.all_operators()]
    assert ('+', 500, 'yfx') in found
    assert ('+', 500, 'fx') in found
    assert ('testop', 400, 'xf') in found
    assert len(found) == len(set(found))
