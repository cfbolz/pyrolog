import py
from rpython.rlib.objectmodel import specialize
from prolog.interpreter import arithmetic
from prolog.interpreter.parsing import TermBuilder
from prolog.interpreter import helper, term, error
from prolog.builtin.register import expose_builtin

# ___________________________________________________________________
# comparison and unification of terms

@expose_builtin("=", unwrap_spec=["raw", "raw"])
def impl_unify(engine, heap, obj1, obj2):
    obj1.unify(obj2, heap)

@expose_builtin("unify_with_occurs_check",
                unwrap_spec=["raw", "raw"])
def impl_unify_with_occurs_check(engine, heap, obj1, obj2):
    obj1.unify(obj2, heap, occurs_check=True)

@expose_builtin("\\=", unwrap_spec=["raw", "raw"])
def impl_does_not_unify(engine, heap, obj1, obj2):
    new_heap = heap.branch()
    try:
        obj1.unify(obj2, new_heap)
    except error.UnificationFailed:
        new_heap.revert_upto(heap)
        return
    new_heap.revert_upto(heap)
    raise error.UnificationFailed()


IDENTITY_BUDGET = 64


class IdentityState(object):
    remaining = 0
    seen = None

    def reset(self):
        self.remaining = IDENTITY_BUDGET
        self.seen = None

    def consume(self):
        self.remaining -= 1
        if self.remaining < 0:
            raise RetryIdentity()


class RetryIdentity(Exception):
    pass


# Identity neither binds variables nor invokes attribute hooks.
identity_state = IdentityState()


@specialize.arg(2)
def identity_visit(left, right, memoized):
    while True:
        if not memoized:
            identity_state.consume()
        if left is right:
            return True
        left_binding = left.getbinding() if isinstance(left, term.Var) else None
        right_binding = right.getbinding() if isinstance(right, term.Var) else None
        if left_binding is None and right_binding is None:
            break
        if memoized:
            # Record before following bindings. One side may be a compound:
            # equivalent cycles need not have their back-edges aligned.
            pair = (left, right)
            seen = identity_state.seen
            if pair in seen:
                return True
            seen[pair] = None
        if left_binding is not None:
            left = left_binding
        if right_binding is not None:
            right = right_binding
    if isinstance(left, term.Var) or isinstance(right, term.Var):
        return False
    if isinstance(left, term.Callable):
        if not isinstance(right, term.Callable):
            return False
        if not left.signature().eq(right.signature()):
            return False
        for i in range(left.argument_count()):
            if not identity_visit(left.argument_at(i), right.argument_at(i), memoized):
                return False
        return True
    if isinstance(right, term.Callable):
        return False
    # Preserve existing atomic equality, including integer representations and
    # float special values. Compound identity no longer depends on ordering.
    return term.cmp_standard_order(left, right, None) == 0


def identical(left, right):
    identity_state.reset()
    try:
        return identity_visit(left, right, False)
    except RetryIdentity:
        identity_state.seen = {}
        try:
            return identity_visit(left, right, True)
        finally:
            identity_state.seen = None


@expose_builtin("==", unwrap_spec=["raw", "raw"])
def impl_identical(engine, heap, obj1, obj2):
    if not identical(obj1, obj2):
        raise error.UnificationFailed()


@expose_builtin("\\==", unwrap_spec=["raw", "raw"])
def impl_not_identical(engine, heap, obj1, obj2):
    if identical(obj1, obj2):
        raise error.UnificationFailed()


def check_order_operand(engine, heap, obj):
    from prolog.builtin.type import impl_acyclic_term
    try:
        impl_acyclic_term(engine, heap, obj)
    except error.UnificationFailed:
        error.throw_domain_error("cyclic_term", obj)


def checked_standard_order(engine, heap, obj1, obj2):
    # Standard order is not well-defined on rational trees. Check both whole
    # operands, even when their outer functors would already decide the order.
    # acyclic_term's budgeted fast path avoids a memo for small finite terms.
    check_order_operand(engine, heap, obj1)
    check_order_operand(engine, heap, obj2)
    return term.cmp_standard_order(obj1, obj2, heap)


for ext, prolog, python in [("lt", "@<", "== -1"),
                            ("le", "@=<", "!= 1"),
                            ("gt", "@>", "== 1"),
                            ("ge", "@>=", "!= -1")]:
    exec py.code.Source("""
@expose_builtin(prolog, unwrap_spec=["obj", "obj"])
def impl_standard_comparison_%s(engine, heap, obj1, obj2):
    c = checked_standard_order(engine, heap, obj1, obj2)
    if not c %s:
        raise error.UnificationFailed()""" % (ext, python)).compile()
 
@expose_builtin("compare", unwrap_spec=["raw", "obj", "obj"])
def impl_compare(engine, heap, result, obj1, obj2):
    c = checked_standard_order(engine, heap, obj1, obj2)
    if c == 0:
        res = term.Callable.build("=")
    elif c == -1:
        res = term.Callable.build("<")
    else:
        res = term.Callable.build(">")
    result.unify(res, heap)
