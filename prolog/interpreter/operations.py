"""Immutable rule code with compiled conjunction, disjunction and conditional branches.

Conditions and other goals remain opaque call templates. Their
arguments are instantiated on demand using the invocation's numbered locals.
The original body remains available for database operations.
"""
from prolog.interpreter.term import Callable, NumberedVar
from prolog.interpreter.signature import Signature

andsig = Signature.getsignature(',', 2)
orsig = Signature.getsignature(';', 2)
ifsig = Signature.getsignature('->', 2)


class Operation(object):
    pass


class CallOperation(Operation):
    _immutable_fields_ = ['template', 'next_pc']

    def __init__(self, template):
        self.template = template
        self.next_pc = 0

    def instantiate(self, heap, locals):
        return self.template.copy_standardize_apart(heap, locals)[0]


class ChoiceOperation(Operation):
    _immutable_fields_ = ['alternative_pc', 'next_pc']

    def __init__(self):
        self.alternative_pc = 0
        self.next_pc = 0


class IfOperation(CallOperation):
    _immutable_fields_ = ['else_pc']

    def __init__(self, condition):
        CallOperation.__init__(self, condition)
        # No else branch: condition failure uses the enclosing failure chain.
        self.else_pc = -1


class JumpOperation(Operation):
    _immutable_fields_ = ['target_pc']

    def __init__(self):
        self.target_pc = 0


def compile_body(body):
    operations = []
    if body is not None:
        _compile_body(body, operations)
    _thread_jumps(operations)
    # Immutable RPython array fields cannot contain a resizable list.
    return operations[:]


def _skip_jump(operations, pc):
    if pc < len(operations):
        operation = operations[pc]
        if isinstance(operation, JumpOperation):
            return operation.target_pc
    return pc


def _thread_jumps(operations):
    # All edges go forward. Resolve from the end, so even nested branch exits
    # reach their final destination with one lookup. A tail call must receive
    # the caller's continuation, not a frame that merely executes a jump.
    for pc in range(len(operations) - 1, -1, -1):
        operation = operations[pc]
        if isinstance(operation, JumpOperation):
            operation.target_pc = _skip_jump(operations, operation.target_pc)
        elif isinstance(operation, ChoiceOperation):
            operation.next_pc = _skip_jump(operations, pc + 1)
            operation.alternative_pc = _skip_jump(operations,
                                                  operation.alternative_pc)
        elif isinstance(operation, IfOperation):
            operation.next_pc = _skip_jump(operations, pc + 1)
            if operation.else_pc >= 0:
                operation.else_pc = _skip_jump(operations, operation.else_pc)
        else:
            assert isinstance(operation, CallOperation)
            operation.next_pc = _skip_jump(operations, pc + 1)


def _compile_body(body, operations):
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
        if isinstance(goal, Callable) and goal.signature().eq(ifsig):
            condition = goal.argument_at(0)
            # Preserve the builtin's validation for variable/invalid conditions.
            if isinstance(condition, Callable):
                operations.append(IfOperation(condition))
                pending.append(goal.argument_at(1))
                continue
        if isinstance(goal, Callable) and goal.signature().eq(orsig):
            left = goal.argument_at(0)
            right = goal.argument_at(1)
            # Variable operands need the existing builtin's eager validation.
            if isinstance(left, Callable) and isinstance(right, Callable):
                if left.signature().eq(ifsig):
                    condition = left.argument_at(0)
                    if not isinstance(condition, Callable):
                        operations.append(CallOperation(goal))
                        continue
                    choice = IfOperation(condition)
                    left = left.argument_at(1)
                else:
                    choice = ChoiceOperation()
                operations.append(choice)
                _compile_body(left, operations)
                jump = JumpOperation()
                operations.append(jump)
                if isinstance(choice, IfOperation):
                    choice.else_pc = len(operations)
                else:
                    assert isinstance(choice, ChoiceOperation)
                    choice.alternative_pc = len(operations)
                _compile_body(right, operations)
                jump.target_pc = len(operations)
                continue
        operations.append(CallOperation(goal))
