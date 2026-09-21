"""Read the line-oriented INRIA test data without parsing its Prolog queries."""
from collections import Counter, namedtuple
import os
import pytest


Case = namedtuple('Case', 'filename lineno query expected setup')


def split_top_level(text, separator=','):
    """Split outside brackets and quotes, including Prolog character literals."""
    parts = []
    stack = []
    quote = None
    start = i = 0
    while i < len(text):
        char = text[i]
        if quote:
            if char == '\\':
                if i + 1 < len(text) and text[i + 1] in 'x01234567':
                    # ISO numeric escapes end with a backslash: '\\xa3\\'.
                    end = text.find('\\', i + 2)
                    assert end != -1, text
                    i = end + 1
                else:
                    i += 2
                continue
            if char == quote:
                if text[i:i + 2] == quote * 2:
                    i += 2
                    continue
                quote = None
        elif text[i:i + 2] == "0'":
            # The character can itself be a quote, comma or bracket.
            i += 2
            if i < len(text) and text[i] == '\\':
                i += 1
            i += 1
            continue
        elif char in ("'", '"'):
            quote = char
        elif char in '([{':
            stack.append(char)
        elif char in ')]}':
            assert stack and stack.pop() == {')': '(', ']': '[', '}': '{'}[char], text
        elif not stack and text.startswith(separator, i):
            parts.append(text[start:i].strip())
            i += len(separator)
            start = i
            continue
        i += 1
    assert not quote and not stack, text
    parts.append(text[start:].strip())
    return parts


def read_cases(directory):
    cases = []
    for filename in sorted(os.listdir(directory)):
        with open(os.path.join(directory, filename)) as source:
            for lineno, line in enumerate(source, 1):
                line = line.strip()
                if not line.startswith('['):
                    continue
                end = line.rfind(']')
                assert end != -1, (filename, lineno, line)
                fields = split_top_level(line[1:end])
                assert len(fields) >= 2, (filename, lineno, line)
                setup = None
                if len(fields) == 3 and fields[1].startswith('setup('):
                    setup = fields[1][6:-1]
                    expected = fields[2]
                else:
                    # Preserve unsupported fixture fields for explicit skips.
                    expected = ', '.join(fields[1:])
                cases.append(Case(filename, lineno, fields[0], expected, setup))
    return cases


def case_key(case):
    query = case.query
    if case.setup is not None:
        query = 'setup(%s), %s' % (case.setup, query)
    return case.filename, query


def parameters(cases, expectations):
    counts = Counter(case_key(case) for case in cases)
    unused = set(expectations) - set(counts)
    assert not unused, 'Unused ISO expectations: %r' % sorted(unused)
    ambiguous = [key for key in expectations if counts[key] != 1]
    assert not ambiguous, 'Ambiguous ISO expectations: %r' % sorted(ambiguous)
    result = []
    for case in cases:
        mark = expectations.get(case_key(case))
        if hasattr(pytest, 'param'):
            result.append(pytest.param(case, marks=mark or ()))
        else:
            # The PyPy checkout bundles pytest 2.9, before pytest.param.
            result.append(mark(case) if mark is not None else case)
    return result


def check_case(case):
    from prolog.interpreter.continuation import Engine
    from prolog.interpreter.test.tool import assert_true, assert_false, prolog_raises

    def new_engine():
        engine = Engine()
        if case.setup is not None:
            assert_true(case.setup + '.', engine)
        return engine

    if case.expected == 'success':
        assert_true(case.query + '.', new_engine())
    elif case.expected == 'failure':
        assert_false(case.query + '.', new_engine())
    elif case.expected.startswith('[') and case.expected.endswith(']'):
        # Preserve the suite's existing check: each expected binding is reachable.
        for solution in split_top_level(case.expected[1:-1]):
            assert solution.startswith('[') and solution.endswith(']'), solution
            bindings = []
            for binding in split_top_level(solution[1:-1]) if solution[1:-1].strip() else []:
                sides = split_top_level(binding, '<--')
                assert len(sides) == 2, binding
                bindings.append(' = '.join(sides))
            query = case.query
            if bindings:
                query += ', ' + ', '.join(bindings)
            # Use a fresh engine for each independent solution check.
            assert_true(query + '.', new_engine())
    elif 'error' in case.expected:
        prolog_raises(case.expected, case.query, new_engine())
    else:
        raise AssertionError('Unsupported ISO expectation: %s' % (case,))
