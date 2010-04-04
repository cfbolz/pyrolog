import py
from prolog.interpreter import helper, term, error, continuation
from prolog.builtin.register import expose_builtin

# ___________________________________________________________________
# operators

@expose_builtin("current_op", unwrap_spec=["obj", "obj", "obj"],
                handles_continuation=True)
def impl_current_op(engine, heap, precedence, typ, name, scont, fcont):
    results = []
    for prec, allops in engine.getoperations():
        for form, ops in allops:
            for op in ops:
                results.append((term.Number(prec),
                                term.Callable.build(form),
                                term.Callable.build(op)))
    results.reverse()
    scont = CurrentOpContinuation(scont, fcont, heap, results,
                                  precedence, typ, name)
    return engine.continue_(scont, fcont, heap.branch())


class CurrentOpContinuation(continuation.ChoiceContinuation):
    def __init__(self, scont, fcont, heap, results, precedence, typ, name):
        continuation.ChoiceContinuation.__init__(self, scont)
        self.undoheap = heap
        self.orig_fcont = fcont
        self.results = results
        self.precedence = precedence
        self.typ = typ
        self.name = name
        
    def activate(self, fcont, heap, engine):
        precedence, typ, name = self.results.pop()
        if self.results:
            fcont, heap = self.prepare_more_solutions(fcont, heap)
        try:
            self.precedence.unify(precedence, heap)
            self.typ.unify(typ, heap)
            self.name.unify(name, heap)
        except error.UnificationFailed:
            return fcont.fail(heap, engine)
        return self.nextcont, fcont, heap


@expose_builtin("op", unwrap_spec=["int", "atom", "atom"])
def impl_op(engine, heap, precedence, typ, name):
    from prolog.interpreter import parsing
    if engine.operations is None:
        engine.operations = parsing.make_default_operations()
    operations = engine.operations
    precedence_to_ops = {}
    for prec, allops in operations:
        precedence_to_ops[prec] = allops
        for form, ops in allops:
            try:
                index = ops.index(name)
                del ops[index]
            except ValueError:
                pass
    if precedence != 0:
        if precedence in precedence_to_ops:
            allops = precedence_to_ops[precedence]
            for form, ops in allops:
                if form == typ:
                    ops.append(name)
                    break
            else:
                allops.append((typ, [name]))
        else:
            for i in range(len(operations)):
                (prec, allops) = operations[i]
                if precedence > prec:
                    operations.insert(i, (precedence, [(typ, [name])]))
                    break
            else:
                operations.append((precedence, [(typ, [name])]))
    engine.parser = parsing.make_parser_at_runtime(engine.operations)


