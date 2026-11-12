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
    return BodyCompiler().compile(body)


class BodyCompiler(object):
    """Build rule operations, then resolve their forward control-flow edges.

    Operations are mutable while being compiled. Only the finished code is
    published to a rule, whose operation array and operation fields are immutable.
    """

    def __init__(self):
        self.operations = []

    def compile(self, body):
        self.operations = []
        if body is not None:
            self._compile_body(body)
        self._thread_jumps()
        # Immutable RPython array fields cannot contain a resizable list.
        return self.operations[:]

    def _compile_body(self, body):
        pending = [body]
        while pending:
            goal = pending.pop()
            if isinstance(goal, Callable) and goal.signature().eq(andsig):
                left = goal.argument_at(0)
                right = goal.argument_at(1)
                # Keep malformed conjunctions opaque: impl_and checks its
                # operands even when the left goal would fail.
                if ((isinstance(left, Callable) or isinstance(left, NumberedVar)) and
                        (isinstance(right, Callable) or isinstance(right, NumberedVar))):
                    pending.append(right)
                    pending.append(left)
                    continue
            if isinstance(goal, Callable) and goal.signature().eq(ifsig):
                condition = goal.argument_at(0)
                # Preserve validation for variable/invalid conditions.
                if isinstance(condition, Callable):
                    self.operations.append(IfOperation(condition))
                    pending.append(goal.argument_at(1))
                    continue
            if isinstance(goal, Callable) and goal.signature().eq(orsig):
                if self._compile_disjunction(goal):
                    continue
            self.operations.append(CallOperation(goal))

    def _compile_disjunction(self, goal):
        """Return False when the disjunction must remain an opaque call."""
        left = goal.argument_at(0)
        right = goal.argument_at(1)
        # Variable operands need the existing builtin's eager validation.
        if not isinstance(left, Callable) or not isinstance(right, Callable):
            return False
        if left.signature().eq(ifsig):
            condition = left.argument_at(0)
            if not isinstance(condition, Callable):
                return False
            choice = IfOperation(condition)
            left = left.argument_at(1)
        else:
            choice = ChoiceOperation()
        self.operations.append(choice)
        alternative_pc = self._compile_branches(left, right)
        if isinstance(choice, IfOperation):
            choice.else_pc = alternative_pc
        else:
            assert isinstance(choice, ChoiceOperation)
            choice.alternative_pc = alternative_pc
        return True

    def _compile_branches(self, left, right):
        """Emit two branches that join at the end; return the right branch PC."""
        self._compile_body(left)
        jump = JumpOperation()
        self.operations.append(jump)
        alternative_pc = len(self.operations)
        self._compile_body(right)
        jump.target_pc = len(self.operations)
        return alternative_pc

    def _thread_jumps(self):
        # All edges go forward. Resolve from the end, so even nested branch
        # exits reach their final destination with one lookup. A tail call
        # must receive the caller's continuation, not a jump-only frame.
        for pc in range(len(self.operations) - 1, -1, -1):
            operation = self.operations[pc]
            if isinstance(operation, JumpOperation):
                operation.target_pc = self._skip_jump(operation.target_pc)
            elif isinstance(operation, ChoiceOperation):
                operation.next_pc = self._skip_jump(pc + 1)
                operation.alternative_pc = self._skip_jump(operation.alternative_pc)
            elif isinstance(operation, IfOperation):
                operation.next_pc = self._skip_jump(pc + 1)
                if operation.else_pc >= 0:
                    operation.else_pc = self._skip_jump(operation.else_pc)
            else:
                assert isinstance(operation, CallOperation)
                operation.next_pc = self._skip_jump(pc + 1)

    def _skip_jump(self, pc):
        if pc < len(self.operations):
            operation = self.operations[pc]
            if isinstance(operation, JumpOperation):
                return operation.target_pc
        return pc
