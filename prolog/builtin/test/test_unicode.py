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
    prolog_raises('type_error(integer, 1.0)', "sub_atom(a,_,1.0,_,_)")
    prolog_raises('type_error(atom, 1)', "sub_atom(a,_,_,_,1)")


def test_unicode_offsets_integer_range():
    huge = '1' + '0' * 100
    assert_false("sub_atom('é',%s,_,_,_)." % huge)
    assert_false("sub_atom('é',_,%s,_,_)." % huge)
    assert_false("atom_length('é',%s)." % huge)
    prolog_raises('domain_error(not_less_than_zero,_)',
                  "sub_atom('é',-%s,_,_,_)" % huge)
    prolog_raises('domain_error(not_less_than_zero,-1)', "atom_length('é',-1)")


@pytest.mark.parametrize('query', [
    "number_chars(N, ['١','٢','٣']), N == 123",
    "number_codes(N, [65297,65298,65299]), N == 123",
    "number_chars(N, [' ','2','3']), N == 23",
    "number_chars(N, ['0', '\\'', '😀']), N == 128512",
    "number_chars(N, ['0', '\\'', 'é']), N == 233",
])
def test_unicode_number_conversion(query):
    assert_true(query + '.')


@pytest.mark.parametrize('query', [
    "findall(B-1-A-S,sub_atom('é😀é',B,1,A,S),R), "
        "R == [0-1-2-'é',1-1-1-'😀',2-1-0-'é']",
    "findall(B-L-S,sub_atom('é😀é',B,L,1,S),R), "
        "R == [0-2-'é😀',1-1-'😀',2-0-'']",
    "findall(L-A-S,sub_atom('é😀é',1,L,A,S),R), "
        "R == [0-2-'',1-1-'😀',2-0-'😀é']",
    "findall(B-L-A,sub_atom('ééé',B,L,A,'éé'),R), "
        "R == [0-2-1,1-2-0]",
    "findall(B-L-A,sub_atom('é😀',B,L,A,''),R), "
        "R == [0-0-2,1-0-1,2-0-0]",
    "findall(B-L-S,sub_atom('é😀é',B,L,B,S),R), "
        "R == [0-3-'é😀é',1-1-'😀']",
    "findall(B-A-S,sub_atom('é😀é',B,B,A,S),R), "
        "R == [0-3-'',1-1-'😀']",
    "findall(B-L-S,sub_atom('é😀é',B,L,L,S),R), "
        "R == [1-1-'😀',3-0-'']",
    "findall(X,sub_atom('é😀é',X,X,X,_),[1])",
    "findall(B,sub_atom('é😀é',B,1,1,'😀'),[1])",
    "findall(S,sub_atom('é😀é',1,_,1,S),['😀'])",
    "findall(S,sub_atom('é😀é',1,2,_,S),['😀é'])",
])
def test_sub_atom_constrained_enumeration(query):
    assert_true(query + '.')


@pytest.mark.parametrize('query', [
    "sub_atom('é😀',_,0,_,'é')", "sub_atom('é😀',_,_,_,'é😀é')",
    "sub_atom('é😀',2,1,_,_)", "sub_atom('é😀',_,2,1,_)",
    "sub_atom('é😀',2,_,1,_)",
])
def test_sub_atom_inconsistent_constraints(query):
    assert_false(query + '.')


def test_sub_atom_unbound_source():
    prolog_raises('instantiation_error', 'sub_atom(_,0,1,0,a)')


def test_sub_atom_fixed_prefix_does_not_scan_whole_atom(monkeypatch):
    from prolog.interpreter import term
    from prolog.interpreter.continuation import Engine
    engine = Engine()
    result = term.BindingVar()
    query = Callable.build('sub_atom', [Callable.build('é' * 10000),
        term.Number(0), term.Number(1), term.Number(9999), result])
    advance = rutf8.next_codepoint_pos
    calls = [0]

    def counted_advance(text, pos):
        calls[0] += 1
        return advance(text, pos)

    monkeypatch.setattr(rutf8, 'next_codepoint_pos', counted_advance)
    engine.run_query_in_current(query)
    assert result.dereference(None).name() == 'é'
    assert calls[0] <= 2
