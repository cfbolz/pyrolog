from prolog.interpreter.continuation import Engine
from prolog.interpreter.test.tool import collect_all, assert_false, assert_true, prolog_raises
import pytest

e = Engine(load_system=True)

@pytest.mark.parametrize('query', [
    'reverse([], X), X == []',
    'reverse([a,b,c], X), X == [c,b,a]',
    'reverse(X, [a,b,c]), X == [c,b,a]',
    'reverse([a,b,c], [c,b,a])',
    'reverse([a|T], [c,b,a]), T == [b,c]',
    'reverse([a,b,c], [c|T]), T == [b,a]',
    'reverse([X,Y,X], [a,b,a]), X == a, Y == b',
    'X = f(X), reverse([X,a], [a,Y]), X == Y',
])
def test_reverse(query):
    assert_true(query + '.', e)


@pytest.mark.parametrize('query', [
    'reverse([a], [])', 'reverse([], [a])',
    'reverse([a,b], [a,b])', 'reverse([a|bad], _)',
    'reverse(_, [a|bad])',
    'X = [a|X], reverse(X, [a,a])',
    'X = [a|X], reverse([a,a], X)',
])
def test_reverse_failure(query):
    assert_false(query + '.', e)


@pytest.mark.parametrize('query', [
    'reverse([a,b,c], X).', 'reverse(X, [a,b,c]).',
    'reverse([a|T], [c,b,a]).', 'reverse([a,b,c], [c|T]).',
])
def test_reverse_exhausts_solutions(query):
    assert len(collect_all(e, query)) == 1


def test_reverse_generates_lists():
    # With two open lists, successively longer solutions remain available.
    assert_true('reverse(X, Y), X = [a,b,c], Y == [c,b,a].', e)

def test_member():
    assert_true("member(1, [1,2,3]).", e)

def test_not_member():
    assert_false("member(666, [661,662,667,689]).", e)

def test_not_member_of_empty():
    assert_false("member(666, []).", e)

def test_all_members():
    data = [ 2**x for x in range(30) ]
    heaps = collect_all(e, "member(X, %s)." % (str(data)))
    nums = [ h["X"].num for h in heaps ]
    assert nums == data

def test_select():
    assert_true("select(1, [1, 2, 3, 1], [2, 3, 1]).", e)
    assert_true("select(1, [1, 2, 3, 1], [1, 2, 3]).", e)
    assert_false("select(1, [1, 2, 3, 1], [1, 2, 3, 1]).", e)
    assert_false("select(1, [1, 2, 3, 1], [2, 3]).", e)
    assert_false("select(2, [], []).", e)
    assert_false("select(2, [], [X]).", e)

def test_nextto():
    assert_true("nextto(666, 1024, [1, 2, 3, 4, 666, 1024, 8, 8, 8]).", e)
    assert_false("nextto(8, 4, [1, 2, 3, 4, 666, 1024, 8, 8, 8]).", e)
    assert_false("nextto(1, 2, [2, 1]).", e)

    heaps = collect_all(e, "nextto(A, B, [1, 2, 3]).")
    assert(len(heaps) == 2)

def test_memberchk():
    assert_true("memberchk(432, [1, 2, 432, 432, 1]).", e)
    assert_false("memberchk(0, [1, 2, 432, 432, 1]).", e)

def test_subtract():
    assert_true("subtract([1, 2, 3, 4], [2], [1, 3, 4]).", e)
    assert_true("subtract([a, c, d], [b], [a, c, d]).", e)
    assert_true("subtract([a, b, c], [], [a, b, c]).", e)
    assert_true("subtract([1, 1, 6], [1, 6], []).", e)

# This is really hard to test as variable addresses can change as their
# binding changes. This is really a problem with @<. See the test for
# this for a counter-example (../interpreter/test/test_standard_order.py).
#
#def test_min_member_var():
#    assert_true("min_member(X, [TEA, UNIVERSE, SHIRT]), " + \
#            "X @=< TEA, X @=< UNIVERSE, X @=< SHIRT.", e)

def test_min_member_number():
    assert_true("min_member(444, [444,445,999]).", e)

def test_min_member_atom():
    assert_true("min_member(fox, [kamikaze,pebble,fox]).", e)

def test_min_member_string():
    assert_true('min_member("fox", ["pebble","fox","foxy","zzz"]).', e)

def test_min_member_term():
    assert_true('min_member(f(x, 3), [g("0", "1", "999"), a(-9, -9, -9), f(x, 3), f(x, 4)]).', e)

def test_min_member_cmp_var_num():
    assert_true('min_member(X, [-999, 10, 20, X]).', e)

def test_min_member_cmp_num_atom():
    assert_true('min_member(1, [a,b,c,1]).', e)

def test_min_member_cmp_atom_string():
    assert_true('min_member(z, ["yeehaw", "blob", z]).', e)

def test_min_member_cmp_string_compund():
    assert_true('min_member("yeehaw", ["yeehaw", flibble(x, b, b), flibble(y, z)]).', e)

def test_min_member_empty():
    assert_false('min_member(X, []).', e)

# Same issue as test_min_member_var. See above.
#def test_max_member_var():
#    assert_true("max_member(X, [TEA,UNIVERSE, SHIRT]), " + \
#            "X @>= TEA, X @>= UNIVERSE, X @>= SHIRT.", e)

def test_max_member_number():
    assert_true("max_member(999, [444,445,999]).", e)

def test_max_member_atom():
    assert_true("max_member(pebble, [kamikaze,pebble,fox]).", e)

def test_max_member_string():
    assert_true('max_member("zzz", ["pebble","fox","foxy","zzz"]).', e)

def test_max_member_term():
    assert_true('max_member(g("0", "1", "999"), [g("0", "1", a), g("0", "1", "999"), a(-9, -9, -9)]).', e)

def test_max_member_cmp_var_num():
    assert_true('max_member(20, [-999, 10, 20, X]).', e)

def test_max_member_cmp_num_atom():
    assert_true('max_member(c, [a,b,c,1]).', e)

def test_max_member_cmp_atom_string():
    assert_true('max_member("yeehaw", ["yeehaw", "blob", z]).', e)

def test_max_member_cmp_string_compund():
    assert_true('max_member(flibble(x, b, b), ["yeehaw", flibble(x, b, b), flibble(y, z)]).', e)

def test_max_member_empty():
    assert_false('max_member(X, []).', e)

def test_delete():
    assert_true('delete([1, 3, 9, 3, 1, 2, 9], 9, [1, 3, 3, 1, 2]).', e)

def test_length():
    assert_true('length([1, a, f(h)], 3).', e)
    assert_true('length([], 0).', e)
    assert_true('length(List, 6), is_list(List), length(List, 6).', e)
    prolog_raises('domain_error(not_less_than_zero, -1)', 'length(X, -1)', e)
    prolog_raises('type_error(list, a)', 'length(a, Y)', e)


@pytest.mark.parametrize('query', [
    'length([a|T], 3), T = [_,_]',
    'length([a|T], N), N = 3, T = [_,_]',
    'length(L, N), N = 3, L = [_,_,_]',
    'length([N], N), N == 1',
    'X = f(X), length([X], N), N == 1',
    'L = [L], length(L, N), N == 1',
])
def test_length_modes(query):
    assert_true(query + '.', e)


@pytest.mark.parametrize('query', [
    'length(L, 0).', 'length(L, 3).', 'length([a|T], 3).',
    'length([a,b], N).',
])
def test_length_exhausts_finite_solutions(query):
    assert len(collect_all(e, query)) == 1


@pytest.mark.parametrize('query', [
    'length(L, L)', 'length([a|N], N)',
    'T = N, length([a,b|T], N)',
    'length([a,b], 1)', 'length([a], 2)',
    'length([], 1000000000000000000000000000000)',
    'length([a], 1000000000000000000000000000000)',
])
def test_length_failure(query):
    assert_false(query + '.', e)


@pytest.mark.parametrize('query, expected', [
    ('length(_, -1)', 'domain_error(not_less_than_zero, -1)'),
    ('length(_, -10000000000000000000000)',
     'domain_error(not_less_than_zero, -10000000000000000000000)'),
    ('length(_, 1.0)', 'type_error(integer, 1.0)'),
    ('length(_, a)', 'type_error(integer, a)'),
    ('length(_, 1+1)', 'type_error(integer, 1+1)'),
    ('length(a, _)', 'type_error(list, a)'),
    ('length([a|bad], _)', 'type_error(list, [a|bad])'),
    ('length([a|bad], 0)', 'type_error(list, [a|bad])'),
    ('length(a, -1)', 'domain_error(not_less_than_zero, -1)'),
])
def test_length_errors(query, expected):
    prolog_raises(expected, query, e)


@pytest.mark.parametrize('setup', ['L = [1|L]', 'T = [b,c|T], L = [a|T]'])
@pytest.mark.parametrize('length', ['N', '0', '5'])
def test_length_cyclic_spine(setup, length):
    assert_true('%s, catch((length(L, %s), fail), error(type_error(list, C)), '
                'C == L).' % (setup, length), e)


@pytest.mark.parametrize('setup', [
    'true', 'L = [a|T]', 'L = a', 'L = [a|bad]',
    'L = [a|L]', 'T = [b,c|T], L = [a|T]',
])
def test_is_list_failure(setup):
    assert_false('%s, is_list(L).' % setup, e)


def test_is_list_does_not_bind_and_ignores_elements():
    assert_true('not(is_list(L)), var(L), '
                'not(is_list([a|T])), var(T).', e)
    assert_true('is_list([]), is_list([X]), var(X), '
                'X = f(X), is_list([X]), L = [L], is_list(L).', e)


def test_is_list_available_without_loading_list_library():
    assert_true('is_list([]), is_list([a,b]), not(is_list(X)), var(X).')

def test_last():
    assert_true('last([1,2,3], 3).', e)
    assert_true('last([666], 666).', e)
    assert_false('last([], X).', e)
