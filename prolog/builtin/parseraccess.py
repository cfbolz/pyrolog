"""Module-local operator declarations and enumeration."""
from prolog.interpreter import helper, term, error, continuation
from prolog.builtin.register import expose_builtin


def _priority(value, minimum):
    if isinstance(value, term.Var):
        error.throw_instantiation_error()
    if isinstance(value, term.BigInt):
        error.throw_domain_error('operator_priority', value)
    if not isinstance(value, term.Number):
        error.throw_type_error('integer', value)
    assert isinstance(value, term.Number)
    if value.num < minimum or value.num > 1200:
        error.throw_domain_error('operator_priority', value)
    return value.num


def _atom(value):
    if isinstance(value, term.Var):
        error.throw_instantiation_error()
    return helper.unwrap_atom(value)


def _form(value):
    form = _atom(value)
    if form not in ('fx', 'fy', 'xf', 'yf', 'xfx', 'xfy', 'yfx'):
        error.throw_domain_error('operator_specifier', value)
    return form


def _qualified_names(engine, heap, module, names):
    while (isinstance(names, term.Callable) and names.name() == ':' and
           names.argument_count() == 2):
        module_name = _atom(names.argument_at(0).dereference(heap))
        module = engine.modulewrapper.get_module(module_name, names)
        names = names.argument_at(1).dereference(heap)
    return module, names


@expose_builtin('op', unwrap_spec=['obj', 'obj', 'obj'], needs_module=True)
def impl_op(engine, heap, module, precedence, typ, names):
    priority = _priority(precedence, 0)
    form = _form(typ)
    module, names = _qualified_names(engine, heap, module, names)
    if isinstance(names, term.Var):
        error.throw_instantiation_error()
    if isinstance(names, term.Atom) and names.name() != '[]':
        values = [names]
    else:
        values = helper.unwrap_list(names)
    for value in values:
        value = value.dereference(heap)
        name = _atom(value)
        if name == ',':
            error.throw_permission_error('modify', 'operator', value)
        if name == '|' and (form not in ('xfx', 'xfy', 'yfx') or
                           0 < priority < 1001):
            error.throw_permission_error('create', 'operator', value)
        if priority == 0:
            module.operators.remove(name, form)
        else:
            module.operators.add(name, priority, form)


@continuation.make_failure_continuation
def continue_current_op(Choice, engine, scont, fcont, heap, operators, index,
                        precedence, typ, name):
    if index < len(operators) - 1:
        fcont = Choice(engine, scont, fcont, heap, operators, index + 1,
                       precedence, typ, name)
        heap = heap.branch()
    operator = operators[index]
    precedence.unify(term.Number(operator.precedence), heap)
    typ.unify(term.Callable.build(operator.form), heap)
    name.unify(term.Callable.build(operator.name), heap)
    return scont, fcont, heap


@expose_builtin('current_op', unwrap_spec=['obj', 'obj', 'obj'],
                needs_module=True, handles_continuation=True)
def impl_current_op(engine, heap, module, precedence, typ, name, scont, fcont):
    priority = -1 if isinstance(precedence, term.Var) else _priority(precedence, 1)
    form = '' if isinstance(typ, term.Var) else _form(typ)
    module, name = _qualified_names(engine, heap, module, name)
    op_name = None if isinstance(name, term.Var) else _atom(name)
    operators = []
    for operator in module.operators.all_operators():
        if (priority == -1 or operator.precedence == priority) and (
                not form or operator.form == form) and (
                op_name is None or operator.name == op_name):
            operators.append(operator)
    if not operators:
        raise error.UnificationFailed
    return continue_current_op(engine, scont, fcont, heap, operators, 0,
                               precedence, typ, name)
