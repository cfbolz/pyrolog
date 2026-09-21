from rpython.rlib.objectmodel import specialize
from prolog.builtin.register import expose_builtin
from prolog.interpreter import term
from prolog.interpreter.helper import wrap_list, is_term, conssig
from prolog.interpreter.memo import CopyMemo
from prolog.interpreter.term import Var, AttVar, Callable
from prolog.interpreter.error import UnificationFailed

@expose_builtin("term_variables", unwrap_spec=["obj", "obj"])
def impl_term_variables(engine, heap, prolog_term, variables):
    term_variables(engine, heap, prolog_term, variables)

@specialize.arg(4)
def term_variables(engine, heap, prolog_term, variables, consider_attributes=False):
    varlist = []
    output_cursor = variables
    seen = {}
    todo = [prolog_term]
    cls = Var
    if consider_attributes:
        cls = AttVar
    while todo:
        value = todo.pop()
        if isinstance(value, Var):
            # Remember variables before following bindings, so back-edges in
            # cyclic terms are skipped as well as repeated free variables.
            if value in seen:
                continue
            seen[value] = None
            binding = value.getbinding()
            if binding is not None:
                todo.append(binding)
                continue
        if isinstance(value, cls):
            if consider_attributes and value.is_empty():
                continue
            # Check capacity without binding output elements: they may alias
            # variables in the input. An open tail imposes no further limit.
            if output_cursor is not None:
                output_cursor = output_cursor.dereference(heap)
                if isinstance(output_cursor, Var):
                    output_cursor = None
                elif (isinstance(output_cursor, Callable) and
                      output_cursor.signature().eq(conssig)):
                    output_cursor = output_cursor.argument_at(1)
                else:
                    raise UnificationFailed()
            varlist.append(value)
        elif isinstance(value, Callable):
            numargs = value.argument_count()
            for i in range(numargs - 1, -1, -1):
                todo.append(value.argument_at(i))
    variables.unify(wrap_list(varlist), heap)
