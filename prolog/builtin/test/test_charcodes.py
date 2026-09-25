import pytest
from prolog.interpreter.test.tool import assert_true, assert_false, prolog_raises


def test_char_code():
    assert_true("char_code(a, Code), Code == 97.")
    assert_true("char_code(Char, 97), Char == a.")
    assert_true("char_code(a, 97).")
    assert_false("char_code(a, 98).")


@pytest.mark.parametrize('code', [0, 1, 127, 128, 163, 255, 256, 0x20ac, 0x1f600, 0x10ffff])
def test_unicode_char_code_roundtrip(code):
    assert_true("char_code(Char, %d), atom_length(Char, 1), "
                "char_code(Char, Code), Code == %d." % (code, code))


@pytest.mark.parametrize('code', [-1, 0xd800, 0xdfff, 0x110000, 10 ** 100])
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
    prolog_raises('representation_error(character_code)', 'atom_codes(Atom, [1114112])')
    prolog_raises('representation_error(character_code)', 'atom_codes(a, [55296])')
    assert_true("atom_codes(Atom, [1,128,255]), atom_codes(Atom, Codes), "
                "Codes == [1,128,255].")


def test_number_codes():
    assert_true("number_codes(45, Codes), Codes == [52,53].")
    assert_true("number_codes(N, [32,45,50,53]), N == -25.")
    assert_true("number_codes(N, [52,46,50,101,43,49]), N == 42.0.")
    assert_true("number_codes(45, [A|Tail]), A == 52, Tail == [53].")
    assert_true("A = 52, Tail = [53], number_codes(N, [A|Tail]), N == 45.")
    assert_false("number_codes(45, [52,54]).")
    assert_false("number_codes(45, [52,53,46,48]).")


@pytest.mark.parametrize('number', ['1000000000000000000000000000000', '1.0e100'])
def test_number_codes_roundtrip(number):
    assert_true("number_codes(%s, Codes), number_codes(N, Codes), N == %s."
                % (number, number))


@pytest.mark.parametrize('codes', ['Codes', '[52,X]', '[52|Tail]'])
def test_number_codes_instantiation(codes):
    prolog_raises('instantiation_error', 'number_codes(N, %s)' % codes)


def test_number_codes_errors():
    prolog_raises('type_error(number, a)', 'number_codes(a, [49])')
    prolog_raises('type_error(integer, a)', 'number_codes(N, [a])')
    prolog_raises('type_error(list, [49|bad])', 'number_codes(N, [49|bad])')
    prolog_raises('syntax_error(E)', 'number_codes(N, [256])')
    prolog_raises('syntax_error(E)', 'number_codes(N, [0])')
    prolog_raises('syntax_error(E)', 'number_codes(N, [45])')
    prolog_raises('syntax_error(E)', 'number_codes(N, [49,32])')


def test_number_chars_completes_partial_list():
    assert_true("number_chars(45, [A|Tail]), A == '4', Tail == ['5'].")


@pytest.mark.parametrize('kind', ['chars', 'codes'])
@pytest.mark.parametrize('text, value', [
    ('0xff', 255), ('0xFf', 255), ('0o77', 63), ('0b101', 5),
    ('+0xff', 255), ('-0xff', -255), ('-0o77', -63), ('+0b101', 5),
    (' \t-0xff', -255), ('0b0', 0), ('-0x0', 0), ('0123', 123),
    ('0x8000000000000000', 2 ** 63),
    ('-0x8000000000000000', -(2 ** 63)),
    ('0x1' + '0' * 25, 2 ** 100),
    ('-0x1' + '0' * 25, -(2 ** 100)),
    ('0o' + '1' + '0' * 40, 8 ** 40),
    ('0b' + '1' + '0' * 100, 2 ** 100),
])
def test_number_conversion_base_prefix(kind, text, value):
    codes = str([ord(c) for c in text])
    assert_true('atom_codes(A, %s), atom_%s(A, L), '
                'number_%s(N, L), N == %s.' % (codes, kind, kind, value))


@pytest.mark.parametrize('kind', ['chars', 'codes'])
@pytest.mark.parametrize('text', [
    '0x', '-0o', '+0b', '0xg', '0o8', '0b2', '0b102',
    '0xff ', '0x ff', '0x+ff', '0x-ff', '0x1.0', '0x1_0',
    '0XFF', '0O77', '0B101', '0xffjunk',
    u'0x\u0661f', u'\u0660x\u0661f',
])
def test_number_conversion_invalid_base_prefix(kind, text):
    codes = str([ord(c) for c in text])
    prolog_raises('syntax_error(_)',
                  'atom_codes(A, %s), atom_%s(A, L), number_%s(N, L)'
                  % (codes, kind, kind))
