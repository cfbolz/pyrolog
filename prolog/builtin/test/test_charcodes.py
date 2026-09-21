import pytest
from prolog.interpreter.test.tool import assert_true, assert_false, prolog_raises


def test_char_code():
    assert_true("char_code(a, Code), Code == 97.")
    assert_true("char_code(Char, 97), Char == a.")
    assert_true("char_code(a, 97).")
    assert_false("char_code(a, 98).")


@pytest.mark.parametrize('code', [1, 127, 128, 163, 255])
def test_byte_char_code_roundtrip(code):
    assert_true("char_code(Char, %d), atom_length(Char, 1), "
                "char_code(Char, Code), Code == %d." % (code, code))


@pytest.mark.parametrize('code', [-1, 0, 256, 1000, 10 ** 100])
def test_invalid_char_code(code):
    prolog_raises('representation_error(character_code)',
                 'char_code(Char, %s)' % code)
    prolog_raises('representation_error(character_code)',
                 'char_code(a, %s)' % code)


@pytest.mark.parametrize('char', ["''", 'ab', '12', 'f(a)', '[]'])
def test_invalid_character(char):
    prolog_raises('type_error(character, %s)' % char,
                 'char_code(%s, Code)' % char)


def test_char_code_instantiation_and_types():
    prolog_raises('instantiation_error', 'char_code(Char, Code)')
    prolog_raises('type_error(integer, a)', 'char_code(Char, a)')
    prolog_raises('type_error(integer, 97.0)', 'char_code(a, 97.0)')


def test_atom_codes():
    assert_true("atom_codes(ab, Codes), Codes == [97,98].")
    assert_true("atom_codes(Atom, [97,98]), Atom == ab.")
    assert_true("atom_codes(Atom, []), Atom == ''.")
    assert_true("atom_codes('', Codes), Codes == [].")
    assert_true("atom_codes([], Codes), Codes == [91,93].")
    assert_true("atom_codes(ab, [A|Tail]), A == 97, Tail == [98].")
    assert_true("A = 97, Tail = [98], atom_codes(Atom, [A|Tail]), Atom == ab.")
    assert_false("atom_codes(ab, [97,99]).")


@pytest.mark.parametrize('codes', ['Codes', '[97,X]', '[97|Tail]'])
def test_atom_codes_instantiation(codes):
    prolog_raises('instantiation_error', 'atom_codes(Atom, %s)' % codes)


def test_atom_codes_validation():
    prolog_raises('type_error(atom, 12)', 'atom_codes(12, [49,50])')
    prolog_raises('type_error(integer, a)', 'atom_codes(Atom, [a])')
    prolog_raises('type_error(integer, 97.0)', 'atom_codes(a, [97.0])')
    prolog_raises('type_error(list, [97|bad])', 'atom_codes(a, [97|bad])')
    prolog_raises('representation_error(character_code)', 'atom_codes(Atom, [256])')
    prolog_raises('representation_error(character_code)', 'atom_codes(a, [0])')
    assert_true("atom_codes(Atom, [1,128,255]), atom_codes(Atom, Codes), "
                "Codes == [1,128,255].")
