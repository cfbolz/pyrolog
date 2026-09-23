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


@pytest.mark.parametrize('query', [
    "sub_atom('aé😀', 1, 1, 1, 'é')",
    "sub_atom('aé😀', B, 1, A, '😀'), B == 2, A == 0",
    "findall(B-L-A-S, sub_atom('é😀',B,L,A,S), R), "
        "R == [0-0-2-'',0-1-1-'é',0-2-0-'é😀',1-0-1-'',1-1-0-'😀',2-0-0-'']",
    "findall(B, sub_atom('ééé',B,2,_, 'éé'), [0,1])",
    "findall(B, sub_atom('é😀',B,0,_, ''), [0,1,2])",
    "sub_atom('é😀',B,L,0,'😀'), B == 1, L == 1",
    "sub_atom('',0,0,0,'')",
])
def test_sub_atom_codepoints(query):
    assert_true(query + '.')


def test_sub_atom_errors_and_failure():
    assert_false("sub_atom('é😀',0,1,0,_).")
    assert_false("sub_atom('é😀',4,_,_,_).")
    prolog_raises('domain_error(not_less_than_zero, -1)', "sub_atom(a,-1,_,_,_)")
    prolog_raises('type_error(integer, x)', "sub_atom(a,_,x,_,_)")
    prolog_raises('type_error(atom, 1)', "sub_atom(a,_,_,_,1)")


@pytest.mark.parametrize('query', [
    "number_chars(N, ['١','٢','٣']), N == 123",
    "number_codes(N, [65297,65298,65299]), N == 123",
    "number_chars(N, [' ','2','3']), N == 23",
    "number_chars(N, ['0', '\\'', '😀']), N == 128512",
    "number_chars(N, ['0', '\\'', 'é']), N == 233",
])
def test_unicode_number_conversion(query):
    assert_true(query + '.')
