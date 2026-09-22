from prolog.interpreter import helper, term, error
from prolog.builtin.register import expose_builtin
from rpython.rlib.objectmodel import specialize

# ___________________________________________________________________
# type verifications

@expose_builtin("nonvar", unwrap_spec=["obj"])
def impl_nonvar(engine, heap, var):
    if isinstance(var, term.Var):
        raise error.UnificationFailed()

@expose_builtin("var", unwrap_spec=["obj"])
def impl_var(engine, heap, var):
    if not isinstance(var, term.Var):
        raise error.UnificationFailed()

@expose_builtin("integer", unwrap_spec=["obj"])
def impl_integer(engine, heap, var):
    if (isinstance(var, term.Var) or not (isinstance(var, term.Number) or
            isinstance(var, term.BigInt))):
        raise error.UnificationFailed()

@expose_builtin("float", unwrap_spec=["obj"])
def impl_float(engine, heap, var):
    if isinstance(var, term.Var) or not isinstance(var, term.Float):
        raise error.UnificationFailed()

@expose_builtin("number", unwrap_spec=["obj"])
def impl_number(engine, heap, var):
    if (isinstance(var, term.Var) or
        (not (isinstance(var, term.Number) or isinstance(var, term.BigInt)) and not
         isinstance(var, term.Float))):
        raise error.UnificationFailed()

@expose_builtin("atom", unwrap_spec=["obj"])
def impl_atom(engine, heap, var):
    if isinstance(var, term.Var) or not isinstance(var, term.Atom):
        raise error.UnificationFailed()

@expose_builtin("atomic", unwrap_spec=["obj"])
def impl_atomic(engine, heap, var):
    if helper.is_atomic(var):
        return
    raise error.UnificationFailed()

@expose_builtin("compound", unwrap_spec=["obj"])
def impl_compound(engine, heap, var):
    if isinstance(var, term.Var):
        raise error.UnificationFailed()
    if helper.is_term(var):
        return
    raise error.UnificationFailed()

@expose_builtin("callable", unwrap_spec=["obj"])
def impl_callable(engine, heap, var):
    if not helper.is_callable(var, engine):
        raise error.UnificationFailed()

GROUND_BUDGET = 64


class GroundState(object):
    remaining = 0
    seen = None

    def reset(self):
        self.remaining = GROUND_BUDGET
        self.seen = None

    def consume(self):
        self.remaining -= 1
        if self.remaining < 0:
            raise RetryGround()


class RetryGround(Exception):
    pass


# ground does not invoke Prolog code or attribute hooks, so this scratch state
# is not reentered. Reset it for each call; allocate a memo only on retry.
ground_state = GroundState()


@specialize.arg(1)
def ground_visit(var, memoized):
    while True:
        if not memoized:
            ground_state.consume()
        if not isinstance(var, term.Var):
            break
        binding = var.getbinding()
        if binding is None:
            raise error.UnificationFailed()
        if memoized:
            seen = ground_state.seen
            if var in seen:
                return
            seen[var] = None
        # Follow bindings explicitly: dereference() would hide the cycle edges.
        var = binding
    if isinstance(var, term.Callable):
        for i in range(var.argument_count()):
            ground_visit(var.argument_at(i), memoized)


@expose_builtin("ground", unwrap_spec=["raw"])
def impl_ground(engine, heap, var):
    ground_state.reset()
    try:
        ground_visit(var, False)
    except RetryGround:
        ground_state.seen = {}
        try:
            ground_visit(var, True)
        finally:
            # Do not retain the term graph between calls, including failures.
            ground_state.seen = None


ACYCLIC_BUDGET = 64


class AcyclicState(object):
    remaining = 0
    seen = None

    def reset(self):
        self.remaining = ACYCLIC_BUDGET
        self.seen = None

    def consume(self):
        self.remaining -= 1
        if self.remaining < 0:
            raise RetryAcyclic()


class RetryAcyclic(Exception):
    pass


# Like ground, this traversal invokes no callbacks and cannot reenter itself.
acyclic_state = AcyclicState()


@specialize.arg(1)
def acyclic_visit(obj, memoized):
    if not memoized:
        acyclic_state.consume()
    binding = None
    if isinstance(obj, term.Var):
        binding = obj.getbinding()
        if binding is None:
            return
    elif not isinstance(obj, term.Callable) or obj.argument_count() == 0:
        return
    if memoized:
        # Copies can share compounds directly, without bound-variable edges.
        # False means active on this path; True means fully checked.
        seen = acyclic_state.seen
        if obj in seen:
            if not seen[obj]:
                raise error.UnificationFailed()
            return
        seen[obj] = False
    if binding is not None:
        acyclic_visit(binding, memoized)
    else:
        assert isinstance(obj, term.Callable)
        for i in range(obj.argument_count()):
            acyclic_visit(obj.argument_at(i), memoized)
    if memoized:
        acyclic_state.seen[obj] = True


@expose_builtin("acyclic_term", unwrap_spec=["raw"])
def impl_acyclic_term(engine, heap, obj):
    acyclic_state.reset()
    try:
        acyclic_visit(obj, False)
    except RetryAcyclic:
        acyclic_state.seen = {}
        try:
            acyclic_visit(obj, True)
        finally:
            acyclic_state.seen = None
