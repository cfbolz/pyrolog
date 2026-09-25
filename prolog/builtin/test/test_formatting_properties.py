"""Round trips for ground, acyclic terms and module-local operator tables.

Generate terms directly: parsing the input could hide writer mistakes.
"""
import pytest
from hypothesis import example, given, settings, strategies as st

from prolog.builtin.formatting import TermFormatter
from prolog.interpreter import term, error
from prolog.interpreter.continuation import Engine
from prolog.interpreter.parsing import parse_query_term


operator_names = st.sampled_from(['p', 'q', '+', '@', '\xe2\x89\xa4', 'has space'])
priorities = st.sampled_from([200, 400, 500, 700, 1000, 1200])
forms = st.sampled_from(['fx', 'fy', 'xf', 'yf', 'xfx', 'xfy', 'yfx'])
declarations = st.lists(
    st.tuples(operator_names, priorities, forms), max_size=6,
    unique_by=lambda definition: (definition[0],
        'infix' if len(definition[2]) == 3 else
        'prefix' if definition[2].startswith('f') else 'postfix'))


def call_trees(children, signatures):
    return st.one_of([
        st.tuples(st.just(name), st.tuples(*([children] * arity)))
        for name, arity in signatures
    ])


@st.composite
def formatting_cases(draw, custom_operators):
    definitions = draw(declarations) if custom_operators else []
    names = ['a', 'b', '[]', 'with space', '\xc3\xa9']
    if custom_operators:
        names += ['+', '\\+']
        names += [name for name, priority, form in definitions]
    leaves = st.one_of(st.sampled_from(names), st.integers(-10, 10))
    signatures = [('f', 1), ('f', 2), (',', 2), ('.', 2), ('\\+', 1), ('+', 2)]
    signatures += [(name, len(form) - 1) for name, priority, form in definitions]
    tree = draw(st.recursive(leaves, lambda children: call_trees(children, signatures),
                             max_leaves=10))
    return definitions, tree


def build_term(tree):
    if isinstance(tree, str):
        return term.Callable.build(tree)
    if isinstance(tree, int):
        return term.Number(tree)
    name, children = tree
    return term.Callable.build(name, [build_term(child) for child in children])


def term_tree(value):
    # Comparing trees detects changed arity/association; comparing printed
    # strings again could let the writer repeat the same mistake twice.
    if isinstance(value, term.Atom):
        return value.name()
    if isinstance(value, term.Number):
        return value.num
    assert isinstance(value, term.Callable), repr(value)
    return value.name(), tuple(term_tree(value.argument_at(i))
                              for i in range(value.argument_count()))


def assert_roundtrip(case, ignore_ops=False):
    definitions, tree = case
    engine = Engine()
    operators = engine.modulewrapper.current_module.operators
    for name, priority, form in definitions:
        operators.add(name, priority, form)
    original = build_term(tree)
    rendered = TermFormatter(engine, quoted=True, ignore_ops=ignore_ops).format(original)
    # Layout prevents a final graphic atom from absorbing the full stop.
    try:
        parsed = parse_query_term(rendered + ' .', operators)
    except error.CatchableError as exc:
        pytest.fail('unreadable output: %r; declarations: %r; tree: %r; error: %s' %
                    (rendered, definitions, tree, exc.get_errstr(engine)))
    assert term_tree(parsed) == tree, (definitions, tree, rendered, term_tree(parsed))


# Start with ordinary atoms and default operators, then introduce custom
# declarations and operator atoms. Separate properties keep ambiguity failures
# from masking basic nesting failures. Canonical notation is a control.
@pytest.mark.parametrize('ignore_ops', [False, True])
@settings(max_examples=300, deadline=None)
@given(case=formatting_cases(custom_operators=False))
@example(case=([], ('\\+', ((',', ('a', 'a')),))))
@example(case=([], ('-', (1,))))
def test_roundtrip_default_operators(ignore_ops, case):
    assert_roundtrip(case, ignore_ops)


@pytest.mark.parametrize('ignore_ops', [False, True])
@settings(max_examples=300, deadline=None)
@given(case=formatting_cases(custom_operators=True))
@example(case=([('p', 200, 'xf')], ('p', ('+',))))
@example(case=([('pre', 500, 'fy'), ('post', 500, 'yf')], ('post', ('pre',))))
@example(case=([('q', 1200, 'xf')], (',', ('a', ('q', ('a',))))))
@example(case=([('q', 1000, 'fx')], (',', ('q', 'a'))))
@example(case=([('p', 200, 'xf'), ('p', 200, 'xfx'), ('+', 400, 'xf')],
              ('+', (('p', ('a',)),))))
def test_roundtrip_custom_operators(ignore_ops, case):
    assert_roundtrip(case, ignore_ops)
