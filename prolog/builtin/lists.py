"""Spine checks for the Prolog list predicates."""
from prolog.builtin.register import expose_builtin
from prolog.builtin.arithmeticbuiltin import check_natural_number
from prolog.interpreter import error, helper, term


@expose_builtin('is_list', unwrap_spec=['obj'])
def impl_is_list(engine, heap, obj):
    tail = helper.list_spine_tail(obj)
    if not (isinstance(tail, term.Callable) and tail.signature().eq(helper.nilsig)):
        raise error.UnificationFailed


@expose_builtin('$check_length_list', unwrap_spec=['obj', 'obj'])
def impl_check_length_list(engine, heap, obj, length):
    check_natural_number(length)
    tail = helper.list_spine_tail(obj)
    if isinstance(tail, term.Var):
        # Completing this tail can never make it an integer. Without this
        # check, length(L,L) and length([a|N],N) would enumerate forever.
        if tail is length:
            raise error.UnificationFailed
    elif not (isinstance(tail, term.Callable) and tail.signature().eq(helper.nilsig)):
        error.throw_type_error('list', obj)
