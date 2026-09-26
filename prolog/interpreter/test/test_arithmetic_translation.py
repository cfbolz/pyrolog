import pytest
from rpython.flowspace.objspace import build_flow

from prolog.interpreter import arithmetic


@pytest.mark.parametrize('helper', [
    arithmetic.bigint_true_divide,
    arithmetic.bigint_trunc_divide,
    arithmetic.bigint_floor_divide,
    arithmetic.bigint_remainder,
])
def test_division_helpers_build_flow_graphs(helper):
    # Python execution alone misses unassigned locals after exception handlers.
    build_flow(helper)
