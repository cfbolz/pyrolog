"""Hypothetical unification without heap writes or attribute hooks."""
from prolog.builtin.register import expose_builtin
from prolog.interpreter import error, helper, term


class Unifier(object):
    def __init__(self):
        self.substitutions = {}
        self.bindings = []
        self.seen = {}

    def resolve(self, obj):
        while True:
            obj = obj.dereference(None)
            if not isinstance(obj, term.Var):
                return obj
            replacement = self.substitutions.get(obj)
            if replacement is None:
                return obj
            obj = replacement

    def unify(self, left, right):
        todo = [(left, right)]
        while todo:
            left, right = todo.pop()
            left = self.resolve(left)
            right = self.resolve(right)
            if left is right:
                continue
            if isinstance(left, term.Var):
                self.bind(left, right)
            elif isinstance(right, term.Var):
                self.bind(right, left)
            elif isinstance(left, term.Callable):
                if (not isinstance(right, term.Callable) or
                        not left.signature().eq(right.signature())):
                    raise error.UnificationFailed
                arity = left.argument_count()
                if arity == 0:
                    continue
                pair = (left, right)
                if pair in self.seen:
                    continue
                self.seen[pair] = None
                for i in range(arity - 1, -1, -1):
                    todo.append((left.argument_at(i), right.argument_at(i)))
            else:
                assert isinstance(left, term.NonVar)
                # Match ordinary atomic unification without hooks or bindings.
                left.atomic_unify(right)

    def bind(self, var, value):
        self.substitutions[var] = value
        # Keep original variables, including rational bindings such as X-f(X).
        self.bindings.append(term.Callable.build('-', [var, value]))


@expose_builtin('unifiable', unwrap_spec=['obj', 'obj', 'raw'])
def impl_unifiable(engine, heap, left, right, result):
    unifier = Unifier()
    unifier.unify(left, right)
    # Preserve the library's reverse discovery order.
    accumulator = helper.emptylist
    for binding in unifier.bindings:
        accumulator = term.Callable.build('.', [binding, accumulator])
    result.unify(accumulator, heap)
