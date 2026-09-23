import pytest
from prolog.interpreter.replpolicy import PrologInputPolicy


@pytest.mark.parametrize('text', [
    'X = f(', 'X = f(a)', 'X = 1.5', 'X =.. [f,a]',
    "X = 'a.b'", 'X = "a.b"', "X = 'a.",
    'true. /* unfinished', 'true % dot in comment.', '/* unfinished.',
])
def test_incomplete(text):
    assert PrologInputPolicy().more_lines(text)


@pytest.mark.parametrize('text', [
    '', '  ', '% comment', '/* comment */',
    'X = f(\na).', 'X = 1.5.', 'X =.. [f,a].',
    "X = 'a.b'.", 'true. % comment', 'true. /* comment */',
    'X = ).', 'f(.', 'X = "a\nb".',
])
def test_complete_or_invalid(text):
    assert not PrologInputPolicy().more_lines(text)
