import py
import pytest
from prolog.interpreter.test.iso import read_cases, parameters, check_case
from prolog.interpreter.test.iso_expectations import EXPECTATIONS

TESTDIR = str(py.path.local(__file__).dirpath().join('inriasuite'))


@pytest.mark.parametrize('case', parameters(read_cases(TESTDIR), EXPECTATIONS),
                         ids=lambda case: '%s:%d' % (case.filename, case.lineno))
def test_all_tests(case):
    check_case(case)
