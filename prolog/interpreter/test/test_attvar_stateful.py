"""Heap operations checked against logical state and saved snapshots."""
from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from prolog.builtin.attvars import impl_del_attr, impl_del_attrs, impl_put_attr
from prolog.interpreter.continuation import FailureContinuation
from prolog.interpreter.heap import Heap
from prolog.interpreter.term import BindingVar, Number


ATTRIBUTE_NAMES = ('m', 'n')


class AttributeStateMachine(RuleBasedStateMachine):
    def __init__(self):
        super(AttributeStateMachine, self).__init__()
        self.heap = Heap()
        self.attvars = [self.heap.new_attvar()]
        self.attributes = [{}]
        self.variables = [self.heap.newvar() for _ in range(3)]
        # Equal ('var', id) tokens denote an unbound alias group. Bound tokens
        # store only the value, never the implementation's binding-chain shape.
        self.bindings = [('var', i) for i in range(len(self.variables))]
        self.snapshots = []
        # Physical undo frames include discarded but retained heaps. They are
        # distinct from the choice points we can still backtrack to.
        self.frames = [self.heap]
        self.marked = set()

    @rule()
    def create_variable(self):
        self.bindings.append(('var', len(self.variables)))
        self.variables.append(self.heap.newvar())

    @rule()
    def create_attvar(self):
        self.attvars.append(self.heap.new_attvar())
        self.attributes.append({})

    def unbound_indices(self):
        return [i for i, token in enumerate(self.bindings) if token[0] == 'var']

    def alias_pairs(self):
        return [(i, j) for i in self.unbound_indices()
                for j in self.unbound_indices()
                if self.bindings[i] != self.bindings[j]]

    # Keep binding mutations below a choice point so backtracking can make
    # variables available for more alias/bind sequences.
    @precondition(lambda self: bool(self.snapshots) and bool(self.alias_pairs()))
    @rule(data=st.data())
    def alias_variables(self, data):
        left, right = data.draw(st.sampled_from(self.alias_pairs()))
        old, new = self.bindings[left], self.bindings[right]
        self.variables[left].unify(self.variables[right], self.heap)
        self.bindings = [new if token == old else token for token in self.bindings]

    @precondition(lambda self: bool(self.snapshots) and bool(self.unbound_indices()))
    @rule(data=st.data(), value=st.integers(-2, 2))
    def bind_variable(self, data, value):
        index = data.draw(st.sampled_from(self.unbound_indices()))
        old = self.bindings[index]
        self.variables[index].unify(Number(value), self.heap)
        self.bindings = [('value', value) if token == old else token
                         for token in self.bindings]

    @rule(data=st.data())
    def compress_variable(self, data):
        index = data.draw(st.integers(0, len(self.variables) - 1))
        self.variables[index].dereference(self.heap)

    @rule(data=st.data(), name=st.sampled_from(ATTRIBUTE_NAMES),
          value=st.integers(-2, 2))
    def put_attribute(self, data, name, value):
        index = data.draw(st.integers(0, len(self.attvars) - 1))
        impl_put_attr(None, self.heap, self.attvars[index], name, Number(value))
        self.attributes[index][name] = value

    @rule(data=st.data(), name=st.sampled_from(ATTRIBUTE_NAMES))
    def delete_attribute(self, data, name):
        index = data.draw(st.integers(0, len(self.attvars) - 1))
        impl_del_attr(None, self.heap, self.attvars[index], name)
        self.attributes[index].pop(name, None)

    @rule(data=st.data())
    def delete_all_attributes(self, data):
        index = data.draw(st.integers(0, len(self.attvars) - 1))
        impl_del_attrs(None, self.heap, self.attvars[index])
        self.attributes[index].clear()

    @rule()
    def create_choice_point(self):
        attributes = [model.copy() for model in self.attributes]
        self.snapshots.append((self.heap, attributes, self.bindings[:]))
        self.heap = self.heap.branch()
        self.frames.append(self.heap)

    @precondition(lambda self: bool(self.snapshots))
    @rule()
    def backtrack(self):
        parent, attributes, bindings = self.snapshots.pop()
        self.heap = self.heap.revert_upto(parent, discard_choicepoint=True)
        self.frames = self.frames[:self.frames.index(parent) + 1]
        self.attributes = attributes
        self.bindings = bindings
        # Variables created since this boundary are no longer live. Cuts keep
        # them available until we backtrack past their creation boundary.
        del self.attvars[len(attributes):]
        del self.variables[len(bindings):]

    @precondition(lambda self: len(self.snapshots) >= 2)
    @rule(data=st.data())
    def cut(self, data):
        count = data.draw(st.integers(1, len(self.snapshots) - 1))
        # Exercise the real continuation cut loop, newest choice point first.
        # Keep an outer boundary; neither live state nor variable lifetimes
        # change until a later backtrack crosses their creation boundary.
        stop = FailureContinuation(None, None, None, None)
        continuation = stop
        for parent, _, _ in self.snapshots[-count:]:
            continuation = FailureContinuation(None, None, continuation, parent)
        # Model the cut walk using frame identities, without consulting prev.
        current = self.heap
        for parent, _, _ in reversed(self.snapshots[-count:]):
            self.marked.add(parent)
            index = self.frames.index(current)
            if index > 0 and self.frames[index - 1] is parent:
                self.frames.remove(parent)
            else:
                current = parent
        continuation.cut(stop, self.heap)
        del self.snapshots[-count:]

    @precondition(lambda self: len(self.snapshots) >= 3)
    @rule(data=st.data())
    def discard_nonadjacent(self, data):
        # Drop an internal choice point while keeping newer ones. The heap
        # must remain on the undo chain until an enclosing rollback or cut.
        index = data.draw(st.integers(1, len(self.snapshots) - 2))
        parent = self.snapshots[index][0]
        assert self.frames.index(parent) < len(self.frames) - 2
        assert parent.discard(self.heap) is parent
        self.marked.add(parent)
        del self.snapshots[index]

    @rule(data=st.data())
    def lookup_owner(self, data):
        variables = self.variables + self.attvars
        index = data.draw(st.integers(0, len(variables) - 1))
        variable = variables[index]
        # Compute the representative without compression. Lookup may rewrite
        # forwarding links, but the physical undo chain must remain intact.
        expected = variable.created_after_choice_point
        seen = set()
        while expected is not None and expected.discarded:
            assert expected not in seen
            seen.add(expected)
            expected = expected.prev
        assert self.heap._is_created_in_self(variable) == (expected is self.heap)
        assert variable.created_after_choice_point is expected

    @invariant()
    def heap_structure_matches_model(self):
        current = self.heap
        for frame in reversed(self.frames):
            assert current is frame
            assert frame.discarded == (frame in self.marked)
            assert 0 <= frame.i <= len(frame.trail_var)
            assert len(frame.trail_var) == len(frame.trail_binding)
            assert len(frame.trail_var) != 1
            assert all(var is not None for var in frame.trail_var[:frame.i])
            current = current.prev
        assert current is None
        # Surviving choice points are an ordered subset of the physical chain.
        indices = [self.frames.index(parent) for parent, _, _ in self.snapshots]
        assert indices == sorted(set(indices))
        assert all(parent not in self.marked for parent, _, _ in self.snapshots)

    @invariant()
    def bindings_match_model(self):
        # Observation must not perform path compression or add trail records.
        actual = [var.dereference(None) for var in self.variables]
        for i, (kind, value) in enumerate(self.bindings):
            if kind == 'value':
                assert isinstance(actual[i], Number)
                assert actual[i].num == value
            else:
                assert isinstance(actual[i], BindingVar)
                assert actual[i].binding is None
                for j in self.unbound_indices():
                    same_group = self.bindings[i] == self.bindings[j]
                    assert (actual[i] is actual[j]) == same_group

    @invariant()
    def attributes_match_model(self):
        for variable, model in zip(self.attvars, self.attributes):
            values = variable.value_list
            if values is not None:
                assert len(values) == len(variable.attmap.indexes)
            assert variable.is_empty() == (not model)
            for name in ATTRIBUTE_NAMES:
                actual = variable.get_attribute_value(name)
                if name in model:
                    assert isinstance(actual, Number)
                    assert actual.num == model[name]
                else:
                    assert actual is None


TestAttributeStateMachine = AttributeStateMachine.TestCase
TestAttributeStateMachine.settings = settings(
    max_examples=1000, stateful_step_count=100, deadline=None)
