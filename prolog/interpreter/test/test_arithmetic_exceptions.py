"""Regressions for host exceptions escaping arithmetic evaluation.

Invalid shifts must raise a catchable Prolog error. Valid comparisons and
large right shifts must return their result rather than raise any error.
"""
import pytest
import subprocess
import sys

from prolog.interpreter.test.tool import assert_true, prolog_raises


BIG = 2 ** 100


@pytest.mark.parametrize('operator', ['<<', '>>'])
@pytest.mark.parametrize('value', [1, BIG])
@pytest.mark.parametrize('count', [-1, -BIG])
def test_negative_shift_error_is_catchable(operator, value, count):
    prolog_raises('domain_error(not_less_than_zero, %s)' % count,
                  'X is %s %s (%s)' % (value, operator, count))


@pytest.mark.parametrize('value', [1, BIG])
def test_oversized_left_shift_error_is_catchable(value):
    # The count cannot fit in a machine integer; do not attempt allocation.
    prolog_raises('representation_error(shift_count)',
                  'X is %s << %s' % (value, BIG))


@pytest.mark.parametrize('value', [1, -1, BIG, -BIG])
def test_oversized_right_shift_returns_sign(value):
    expected = -1 if value < 0 else 0
    assert_true('X is (%s) >> %s, X = %s.' % (value, BIG, expected))


@pytest.mark.parametrize('operator', ['+', '-', '*', '/', 'max', 'min'])
@pytest.mark.parametrize('bigint_first', [False, True])
def test_mixed_float_bigint_overflow_is_catchable(operator, bigint_first):
    operands = [str(10 ** 400), '1.0']
    if not bigint_first:
        operands.reverse()
    left, right = operands
    if operator in ['max', 'min']:
        expression = '%s(%s, %s)' % (operator, left, right)
    else:
        expression = '%s %s %s' % (left, operator, right)
    prolog_raises('evaluation_error(float_overflow)', 'X is %s' % expression)


@pytest.mark.parametrize('operator', ['=:=', '=\\=', '<', '=<', '>', '>='])
@pytest.mark.parametrize('left,right', [
    (BIG, 1), (1, BIG), (BIG, 1.0), (1.0, BIG),
    (BIG, BIG), (BIG, BIG + 1),
])
def test_bigint_comparison_does_not_raise(operator, left, right):
    expected = {
        '=:=': left == right,
        '=\\=': left != right,
        '<': left < right,
        '=<': left <= right,
        '>': left > right,
        '>=': left >= right,
    }[operator]
    assert_true('((%s %s %s) -> R = yes; R = no), R = %s.' %
                (left, operator, right, 'yes' if expected else 'no'))


@pytest.mark.parametrize('operator', ['<<', '>>'])
@pytest.mark.parametrize('left,right', [('1.0', '2'), ('1', '2.0')])
def test_shift_requires_integer_operands(operator, left, right):
    culprit = left if left == '1.0' else right
    prolog_raises('type_error(integer, %s)' % culprit,
                  'X is %s %s %s' % (left, operator, right))


@pytest.mark.parametrize('operator', ['mod', '/\\', '\\/', 'xor'])
@pytest.mark.parametrize('left,right,culprit', [
    ('1.25', '2', '1.25'),
    ('2', '1.25', '1.25'),
    ('1.25', str(BIG), '1.25'),
    (str(BIG), '1.25', '1.25'),
    ('1.25', '2.5', '1.25'),
    ('1.25', '0', '1.25'),
    ('2', '(1 / 2.0)', '0.5'),
])
def test_integer_only_binary_float_error(operator, left, right, culprit):
    assert_true(
        'catch((X is %s %s %s, fail), '
        'error(type_error(integer, %s)), true), Y is 2 + 3, Y = 5.' %
        (left, operator, right, culprit))


@pytest.mark.parametrize('expression,culprit', [
    ('1.25', '1.25'), ('-1.25', '-1.25'), ('(1 / 2.0)', '0.5'),
])
def test_integer_complement_float_error(expression, culprit):
    prolog_raises('type_error(integer, %s)' % culprit,
                  'X is \\ (%s)' % expression)


def test_gigantic_left_shift_allocation_error_is_catchable():
    if not sys.platform.startswith('linux'):
        pytest.skip('uses /proc to set an allocation limit above current usage')
    code = r'''
import os
import resource
import sys
from prolog.interpreter.continuation import Engine
from prolog.interpreter.test.tool import assert_true

engine = Engine()
assert_true('true.', engine)
queries = []
for value in [1, -1, 2 ** 100, -(2 ** 100)]:
    for count in [sys.maxint, sys.maxint - 1]:
        query = ('catch((X is (%s) << %s, fail), '
                 'error(resource_error(memory)), true).') % (value, count)
        queries.append(engine.parse(query)[0][0])
with open('/proc/self/statm') as status:
    virtual_bytes = int(status.read().split()[0]) * os.sysconf('SC_PAGE_SIZE')
limit = virtual_bytes + 32 * 1024 * 1024
_, hard = resource.getrlimit(resource.RLIMIT_AS)
if hard != resource.RLIM_INFINITY:
    limit = min(limit, hard)
resource.setrlimit(resource.RLIMIT_AS, (limit, hard))
resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
for query in queries:
    engine.run_query_in_current(query)
# Recovery must leave the engine usable, and shifting zero needs no allocation.
assert_true('X is 2 + 3, X = 5.', engine)
assert_true('X is 0 << %s, X = 0.' % sys.maxint, engine)
print('recovered')
'''
    process = subprocess.Popen([sys.executable, '-c', code],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    assert process.returncode == 0, stderr
    assert stdout.strip() == 'recovered'


@pytest.mark.parametrize('value', [1, BIG])
def test_left_shift_allocation_failure(value, monkeypatch):
    from rpython.rlib.rbigint import rbigint

    def no_memory(*args):
        raise MemoryError

    monkeypatch.setattr(rbigint, 'lshift', no_memory)
    monkeypatch.setattr(rbigint, 'lshift_int_int_bigint_result',
                        staticmethod(no_memory))
    prolog_raises('resource_error(memory)', 'X is %s << 100' % value)
