"""Immutable rule code; only conjunction has a compiled control-flow form.

Other goals (including control builtins) remain opaque call templates. Their
arguments are instantiated on demand using the invocation's numbered locals.
The original body remains available for database operations.
"""
from prolog.interpreter.term import Callable, NumberedVar
from prolog.interpreter.signature import Signature

andsig = Signature.getsignature(',', 2)


class CallOperation(object):
    _immutable_fields_ = ['template']

    def __init__(self, template):
        self.template = template

    def instantiate(self, heap, locals):
        return self.template.copy_standardize_apart(heap, locals)[0]


def compile_body(body):
    operations = []
    if body is None:
        return operations[:]
    pending = [body]
    while pending:
        goal = pending.pop()
        if isinstance(goal, Callable) and goal.signature().eq(andsig):
            left = goal.argument_at(0)
            right = goal.argument_at(1)
            # Keep malformed conjunctions opaque: impl_and checks its operands
            # before executing the left goal, even when that goal would fail.
            if ((isinstance(left, Callable) or isinstance(left, NumberedVar)) and
                    (isinstance(right, Callable) or isinstance(right, NumberedVar))):
                pending.append(right)
                pending.append(left)
                continue
        operations.append(CallOperation(goal))
    # Immutable RPython array fields cannot contain a resizable list.
    return operations[:]
