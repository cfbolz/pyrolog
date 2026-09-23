# coding: utf-8
import pytest
from rpython.rlib import rutf8
from prolog.interpreter.term import Callable
from prolog.interpreter.test.tool import assert_true, assert_false, prolog_raises


@pytest.mark.parametrize('query', [
    "atom_length('aé€😀', 4)",
    "atom_codes('aé€😀', [97,233,8364,128512])",
    "atom_codes(A, [97,233,8364,128512]), A == 'aé€😀'",
    "atom_chars('aé€😀', [a,'é','€','😀'])",
    "atom_chars(A, [a,'é','€','😀']), A == 'aé€😀'",
    "atom_chars('é😀', [X|Xs]), X == 'é', Xs == ['😀']",
    "char_code('😀', 128512)",
    "char_code(C, 0), atom_codes(C, [0]), atom_length(C, 1)",
    "findall(A-B, atom_concat(A,B,'é😀'), L), "
        "L == [''-'é😀','é'-'😀','é😀'-'']",
    "atom_concat('é', B, 'é😀'), B == '😀'",
    "atom_concat(A, '😀', 'é😀'), A == 'é'",
    "atom_length('é', 2), 'é' \\== 'é'",
    "'é' @< '€', '€' @< '😀'",
])
def test_unicode_atoms(query):
    assert_true(query + '.')


@pytest.mark.parametrize('raw', ['\xff', '\xc0\x80', '\xed\xa0\x80', '\xf4\x90\x80\x80', '\xe2\x82'])
def test_atom_rejects_invalid_utf8(raw):
    with pytest.raises(rutf8.CheckError):
        Callable.build(raw)


def test_combining_sequence_is_not_one_character():
    prolog_raises("type_error(character, 'é')", "char_code('é', C)")
