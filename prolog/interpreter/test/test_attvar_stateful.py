"""Attribute operations checked against a dictionary and saved snapshots."""
from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from prolog.builtin.attvars import impl_del_attr, impl_del_attrs, impl_put_attr
from prolog.interpreter.heap import Heap
from prolog.interpreter.term import Number


ATTRIBUTE_NAMES = ('m', 'n')


class AttributeStateMachine(RuleBasedStateMachine):
    def __init__(self):
        super(AttributeStateMachine, self).__init__()
        self.heap = Heap()
        self.variable = self.heap.new_attvar()
        self.model = {}
        self.snapshots = []

    @rule(name=st.sampled_from(ATTRIBUTE_NAMES), value=st.integers(-2, 2))
    def put_attribute(self, name, value):
        impl_put_attr(None, self.heap, self.variable, name, Number(value))
        self.model[name] = value

    @rule(name=st.sampled_from(ATTRIBUTE_NAMES))
    def delete_attribute(self, name):
        impl_del_attr(None, self.heap, self.variable, name)
        self.model.pop(name, None)

    @rule()
    def delete_all_attributes(self):
        impl_del_attrs(None, self.heap, self.variable)
        self.model.clear()

    @rule()
    def create_choice_point(self):
        self.snapshots.append((self.heap, self.model.copy()))
        self.heap = self.heap.branch()

    @precondition(lambda self: bool(self.snapshots))
    @rule()
    def backtrack(self):
        parent, model = self.snapshots.pop()
        self.heap = self.heap.revert_upto(parent, discard_choicepoint=True)
        self.model = model

    @precondition(lambda self: len(self.snapshots) >= 2)
    @rule()
    def cut(self):
        # Remove the inner restoration boundary, retaining the outer snapshot.
        # The live attributes do not change, and the root heap is never cut.
        discarded, _ = self.snapshots.pop()
        current = self.heap
        self.heap = discarded.discard(current)
        assert self.heap is current
        assert self.heap.prev is self.snapshots[-1][0]

    @invariant()
    def attributes_match_model(self):
        values = self.variable.value_list
        if values is not None:
            assert len(values) == len(self.variable.attmap.indexes)
        assert self.variable.is_empty() == (not self.model)
        for name in ATTRIBUTE_NAMES:
            actual = self.variable.get_attribute_value(name)
            if name in self.model:
                assert isinstance(actual, Number)
                assert actual.num == self.model[name]
            else:
                assert actual is None


TestAttributeStateMachine = AttributeStateMachine.TestCase
TestAttributeStateMachine.settings = settings(
    max_examples=100, stateful_step_count=50, deadline=None)
