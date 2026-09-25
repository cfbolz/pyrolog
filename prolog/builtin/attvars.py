from prolog.builtin.register import expose_builtin
from prolog.interpreter import continuation
from prolog.interpreter.term import AttVar, Var, Callable, Atom
from prolog.interpreter.error import UnificationFailed,\
throw_representation_error, throw_instantiation_error
from prolog.interpreter.helper import wrap_list, is_term, unwrap_list
from prolog.interpreter.signature import Signature
from prolog.builtin.term_variables import term_variables

conssig = Signature.getsignature(".", 2)

@expose_builtin("attvar", unwrap_spec=["obj"])
def impl_attvar(engine, heap, obj):
    if not isinstance(obj, AttVar):
        raise UnificationFailed()
    if obj.is_empty():
        raise UnificationFailed()
        
@expose_builtin("put_attr", unwrap_spec=["obj", "atom", "obj"])
def impl_put_attr(engine, heap, var, attr, value):
    if isinstance(var, AttVar):
        old_value, _ = var.get_attribute(attr)
        var.add_attribute(attr, value)
        _, index = var.get_attribute(attr)
        heap.trail_new_attr(var, index, old_value)
    elif isinstance(var, Var):
        attvar = heap.new_attvar()
        attvar.add_attribute(attr, value)
        var.unify(attvar, heap)
    else:
        throw_representation_error("put_attr/3",
                "argument must be unbound (1-st argument)")

@expose_builtin("get_attr", unwrap_spec=["obj", "atom", "obj"])
def impl_get_attr(engine, heap, var, attr, value):
    if not isinstance(var, Var):
        throw_instantiation_error(var)
    if not isinstance(var, AttVar):
        raise UnificationFailed()
    attribute_value = var.get_attribute_value(attr)
    if attribute_value is not None:
        value.unify(attribute_value, heap)
    else:
        raise UnificationFailed()
 
@expose_builtin("del_attr", unwrap_spec=["obj", "atom"])
def impl_del_attr(engine, heap, var, attr):
    if isinstance(var, AttVar) and var.get_attribute_value(attr) is not None:
        heap.add_trail_atts(var, attr)
        var.del_attribute(attr)

@expose_builtin("term_attvars", unwrap_spec=["obj", "obj"])
def impl_term_attvars(engine, heap, prolog_term, variables):
    term_variables(engine, heap, prolog_term, variables, True)

def attributed_variables(engine, heap, value):
    X = heap.newvar()
    impl_term_attvars(engine, heap, value, X)
    return unwrap_list(X.dereference(heap))


attribute_goals_signature = Signature.getsignature('attribute_goals', 3)


class UnifyCopyResultContinuation(continuation.Continuation):
    def __init__(self, engine, nextcont, bag, copy, goals):
        continuation.Continuation.__init__(self, engine, nextcont)
        self.bag = bag
        self.expected = wrap_list([Callable.build('-', [copy, goals])])

    def activate(self, fcont, heap):
        # Match outputs in the driver, after rollback. A mismatch must follow
        # normal Prolog failure handling rather than escape a failure callback.
        self.bag.unify(self.expected, heap)
        return self.nextcont, fcont, heap


class AttributeGoalsContinuation(continuation.Continuation):
    """Project attributes inside a findall rollback boundary.

    Each hook is committed to its first success before returning here, so
    projection progress is private to this invocation and is not backtracked.
    """
    def __init__(self, engine, nextcont, template, variables, goals):
        continuation.Continuation.__init__(self, engine, nextcont)
        self.template = template
        self.variables = variables
        self.goals = goals
        self.variable_index = 0
        self.attributes = []
        self.attribute_index = 0
        self.current_variable = None
        self.chunk = None
        self.collected = []

    def activate(self, fcont, heap):
        if self.chunk is not None:
            self.collected.extend(unwrap_list(self.chunk))
            self.chunk = None
        while True:
            if self.attribute_index == len(self.attributes):
                if self.variable_index == len(self.variables):
                    break
                variable = self.variables[self.variable_index].dereference(heap)
                self.variable_index += 1
                self.attributes = []
                self.attribute_index = 0
                if not isinstance(variable, AttVar) or variable.is_empty():
                    continue
                self.current_variable = variable
                # Snapshot this variable's attributes, as SWI's get_attrs/2
                # does. Later variables are inspected after earlier hooks run.
                for module, index in variable.attmap.indexes.iteritems():
                    value = variable.value_list[index]
                    if value is not None:
                        self.attributes.append((module, value))
                continue
            variable = self.current_variable
            assert variable is not None
            module_name, value = self.attributes[self.attribute_index]
            self.attribute_index += 1
            if not isinstance(variable.dereference(heap), Var):
                continue  # An earlier hook may have instantiated this variable.
            fallback = Callable.build('put_attr', [variable,
                                      Callable.build(module_name), value])
            module = self.engine.modulewrapper.modules.get(module_name)
            if module is None or module.lookup(attribute_goals_signature) is None:
                self.collected.append(fallback)
                continue
            self.chunk = heap.newvar()
            hook = Callable.build('attribute_goals', [variable, self.chunk,
                                                      wrap_list([])])
            # A failing hook falls back; a successful hook contributes its
            # first solution only. The normal control continuations do both.
            query = Callable.build(';', [
                Callable.build('->', [hook, Callable.build('true')]),
                Callable.build('=', [self.chunk, wrap_list([fallback])])])
            return self.engine.call_in_module(query, module, self, fcont, heap)
        self.goals.unify(wrap_list(self.collected), heap)
        # The collector copies the term and goals together. Remove attributes
        # only temporarily, including attributes on variables in emitted goals.
        for variable in attributed_variables(self.engine, heap, self.template):
            impl_del_attrs(self.engine, heap, variable)
        return self.nextcont, fcont, heap


@expose_builtin("copy_term", unwrap_spec=["obj", "obj", "obj"],
                handles_continuation=True)
def impl_copy_term_3(engine, heap, prolog_term, copy, goals, scont, fcont):
    from prolog.interpreter.memo import CopyMemo
    from prolog.builtin.allsolution import FindallContinuation, DoneWithFindallContinuation
    variables = attributed_variables(engine, heap, prolog_term)
    if not variables:
        prolog_term.copy(heap, CopyMemo()).unify(copy, heap)
        goals.unify(wrap_list([]), heap)
        return scont, fcont, heap
    residuals = heap.newvar()
    template = Callable.build('-', [prolog_term, residuals])
    bag = heap.newvar()
    result = UnifyCopyResultContinuation(engine, scont, bag, copy, goals)
    collector = FindallContinuation(engine, template, heap, result)
    done = DoneWithFindallContinuation(engine, result, fcont, heap, collector, bag)
    project = AttributeGoalsContinuation(engine, collector, template, variables, residuals)
    return project, done, heap.branch()

@expose_builtin("del_attrs", unwrap_spec=["obj"])
def impl_del_attrs(engine, heap, attvar):
    if isinstance(attvar, AttVar):
        if attvar.value_list is not None:
            for name, index in attvar.attmap.indexes.iteritems():
                heap.add_trail_atts(attvar, name)
            attvar.value_list = None
