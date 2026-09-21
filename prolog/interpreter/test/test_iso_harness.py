import os
import subprocess
import sys
import pytest
from prolog.interpreter.test.test_iso import (
    Case, case_key, check_case, parameters, read_cases, split_top_level,
)


@pytest.mark.parametrize('text, expected', [
    ("p(a, [b,c]), success", ["p(a, [b,c])", "success"]),
    ("undef_pred, existence_error(procedure, undef_pred/0)",
     ["undef_pred", "existence_error(procedure, undef_pred/0)"]),
    ("[X <-- 1],[X <-- 2]", ["[X <-- 1]", "[X <-- 2]"]),
    ("'a,b', '''', f(']')", ["'a,b'", "''''", "f(']')"]),
    (r"'\xa3\', x", [r"'\xa3\'", "x"]),
    ("0',, 0'[, 0'], 0''", ["0',", "0'[", "0']", "0''"]),
    ('X = "a,b", success', ['X = "a,b"', 'success']),
])
def test_split_fields(text, expected):
    assert split_top_level(text) == expected


def test_read_cases_preserves_real_queries(tmpdir):
    tmpdir.join('example').write(
        '/* current_prolog_flag is mentioned only in this comment */\n'
        "[number_chars(33.0,L), [[L <-- ['3','3','.','0']]]].\n"
        '[undef_pred, existence_error(procedure,undef_pred/0)].\n'
        '[X = "fred", setup(set_prolog_flag(double_quotes, atom)), '
        '[[X <-- fred]]].\n')
    cases = read_cases(str(tmpdir))
    assert len(cases) == 3
    assert cases[0].query == 'number_chars(33.0,L)'
    assert cases[1].query == 'undef_pred'
    assert cases[2].setup == 'set_prolog_flag(double_quotes, atom)'
    assert case_key(cases[2]) == (
        'example', 'setup(set_prolog_flag(double_quotes, atom)), X = "fred"')


def test_marks_do_not_depend_on_line_or_expected_answer():
    first = Case('example', 1, 'p(X)', 'success', None)
    moved = first._replace(lineno=20, expected='failure')
    mark = pytest.mark.xfail(reason='known gap', strict=True)
    expectations = {case_key(first): mark}
    assert parameters([moved], expectations)


def test_reject_stale_or_ambiguous_expectations():
    case = Case('example', 1, 'p(X)', 'success', None)
    mark = pytest.mark.xfail(reason='known gap', strict=True)
    with pytest.raises(AssertionError, match='Unused ISO expectations'):
        parameters([case], {('example', 'removed'): mark})
    with pytest.raises(AssertionError, match='Ambiguous ISO expectations'):
        parameters([case, case._replace(lineno=2)], {case_key(case): mark})


def test_solution_lists_without_spaces():
    check_case(Case('example', 1, '((X=1;X=2), \\+((!,fail)))',
                    '[[X <-- 1],[X <-- 2]]', None))


def test_setup_runs_before_query_on_same_engine():
    # An observable setup using functionality already implemented.
    check_case(Case('example', 1, 'p(X)', '[[X <-- a]]', 'assertz(p(a))'))


def test_unknown_expectation_fails():
    with pytest.raises(AssertionError, match='Unsupported ISO expectation'):
        check_case(Case('example', 1, 'true', 'typo', None))


def test_marked_cases_keep_strict_outcomes(tmpdir):
    testfile = tmpdir.join('test_marks.py')
    testfile.write("""
import pytest
from prolog.interpreter.test.test_iso import Case, case_key, parameters

cases = [Case('example', n, name, 'success', None)
         for n, name in enumerate(['fixed', 'different', 'known', 'fixture'])]
marks = dict((case_key(case),
              pytest.mark.xfail(reason='known gap', strict=True, raises=ValueError))
             for case in cases[:3])
marks[case_key(cases[3])] = pytest.mark.skip(reason='missing fixture')

@pytest.mark.parametrize('case', parameters(cases, marks))
def test_case(case):
    if case.query == 'different':
        raise TypeError('unrelated regression')
    if case.query == 'known':
        raise ValueError('known gap')
    if case.query == 'fixture':
        raise AssertionError('must not execute')
""")
    # Keep the same pytest version as the parent, including PyPy's bundled one.
    code = ('import sys; sys.path.insert(0, %r); import pytest; '
            'sys.exit(pytest.main(["-q", %r]))') % (
                os.path.dirname(pytest.__file__), str(testfile))
    process = subprocess.Popen([sys.executable, '-c', code],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output, _ = process.communicate()
    assert process.returncode == 1, output
    assert '2 failed, 1 skipped, 1 xfailed' in output, output
    assert 'XPASS(strict)' in output, output
    assert 'unrelated regression' in output, output
