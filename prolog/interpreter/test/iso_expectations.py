"""Known ISO gaps, keyed by suite filename and query (including explicit setup).

Expected answers live only in inriasuite/. Keep marks specific: unexpected passes
and exceptions of an unrelated type must fail. Collection rejects stale or
ambiguous keys.
"""
import pytest
from prolog.interpreter.error import (
    PrologParseError, UncaughtError, UnificationFailed,
)


def xfail(reason, raises):
    return pytest.mark.xfail(reason=reason, raises=raises, strict=True)


def skip(reason):
    return pytest.mark.skip(reason=reason)


EXPECTATIONS = {
    ('abolish', '(current_prolog_flag(max_arity,A), X is A + 1, abolish(foo/X))'):
        xfail('current_prolog_flag/2 is not implemented', UncaughtError),
    ('arg', 'arg(X,foo(a,b),a)'):
        xfail('arg/3 enumerates arguments for an unbound index', UnificationFailed),
    ('arg', 'arg(0,atom,A)'):
        xfail('arg/3 fails on atoms instead of raising type_error(compound, ...)', UnificationFailed),
    ('asserta', '(asserta((bar(X) :- X)), clause(bar(X), B))'):
        xfail('Asserting a variable clause body raises instantiation_error instead of wrapping call/1', UncaughtError),
    ('atom_chars', "atom_chars('''',L)"):
        xfail('Parser does not support doubled quotes in quoted atoms', PrologParseError),
    ('atom_codes', 'atom_codes([],L)'):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('atom_codes', "atom_codes('''',L)"):
        xfail('Parser does not support doubled quotes in quoted atoms', PrologParseError),
    ('atom_codes', "atom_codes('iso',L)"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('atom_codes', "atom_codes(A,[ 0'p, 0'r, 0'o, 0'l, 0'o, 0'g])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('atom_codes', "atom_codes('North',[0'N | L])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('atom_codes', "atom_codes('iso',[0'i, 0's])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('atom_codes', "atom_codes(A, 0'x)"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('atom_codes', "atom_codes(A,[ 0'i, 0's, 1000])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('bagof', 'bagof(X,(X=1;X=2),L)'):
        xfail('bagof/3 is not implemented', UncaughtError),
    ('bagof', 'bagof(X,(X=1;X=2),X)'):
        xfail('bagof/3 is not implemented', UncaughtError),
    ('bagof', 'bagof(X,(X=Y;X=Z),L)'):
        xfail('bagof/3 is not implemented', UncaughtError),
    ('bagof', 'bagof(X,fail,L)'):
        xfail('bagof/3 is not implemented', UncaughtError),
    ('bagof', 'bagof(1,(Y=1;Y=2),L)'):
        xfail('bagof/3 is not implemented', UncaughtError),
    ('bagof', 'bagof(f(X,Y),(X=a;Y=b),L)'):
        xfail('bagof/3 is not implemented', UncaughtError),
    ('bagof', 'bagof(X,Y^((X=1,Y=1);(X=2,Y=2)),S)'):
        xfail('bagof/3 is not implemented', UncaughtError),
    ('bagof', 'bagof(X,Y^((X=1;Y=1);(X=2,Y=2)),S)'):
        xfail('bagof/3 is not implemented', UncaughtError),
    ('bagof', '(set_prolog_flag(unknown, warning), bagof(X,(Y^(X=1;Y=1);X=3),S))'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('bagof', 'bagof(X,(X=Y;X=Z;Y=1),L)'):
        xfail('bagof/3 is not implemented', UncaughtError),
    ('bagof', 'bagof(X,Y^Z,L)'):
        xfail('bagof/3 is not implemented', UncaughtError),
    ('bagof', 'bagof(X,1,L)'):
        xfail('bagof/3 is not implemented', UncaughtError),
    ('call', 'call((fail, 1))'):
        xfail('call/1 reports the nested invalid term rather than the enclosing goal as the error culprit', UncaughtError),
    ('call', 'call((write(3), 1))'):
        xfail('call/1 reports the nested invalid term rather than the enclosing goal as the error culprit', UncaughtError),
    ('call', 'call((1; true))'):
        xfail('call/1 reports the nested invalid term rather than the enclosing goal as the error culprit', UncaughtError),
    ('catch-and-throw', "(catch(true, C, write('something')), throw(blabla))"):
        skip('Requires the original outer runner to map uncaught throws to system_error'),
    ('catch-and-throw', 'catch(number_chars(A,L), error(instantiation_error, _), fail)'):
        xfail('Errors use error/1 instead of the expected error/2 with context', UncaughtError),
    ('char_code', 'char_code(a,Code)'):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('char_code', "char_code(Char,0'c)"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('char_code', 'char_code(Char,163)'):
        xfail('Quoted atoms do not decode numeric character escapes', UnificationFailed),
    ('clause', 'clause(x,Body)'):
        xfail('clause/2 is not implemented', UncaughtError),
    ('clause', 'clause(_,B)'):
        xfail('clause/2 is not implemented', UncaughtError),
    ('clause', 'clause(4,B)'):
        xfail('clause/2 is not implemented', UncaughtError),
    ('clause', 'clause(f(_),5)'):
        xfail('clause/2 is not implemented', UncaughtError),
    ('clause', 'clause(atom(_),Body)'):
        xfail('clause/2 is not implemented', UncaughtError),
    ('current_input', 'exists(current_input/1)'):
        xfail('Missing INRIA exists/1 helper; current stream predicates themselves exist', UncaughtError),
    ('current_output', 'exists(current_output/1)'):
        xfail('Missing INRIA exists/1 helper; current stream predicates themselves exist', UncaughtError),
    ('current_predicate', 'current_predicate(current_predicate/1)'):
        xfail('current_predicate/1 is not implemented', UncaughtError),
    ('current_predicate', 'current_predicate(run_tests/1)'):
        xfail('current_predicate/1 is not implemented', UncaughtError),
    ('current_predicate', 'current_predicate(4)'):
        xfail('current_predicate/1 is not implemented', UncaughtError),
    ('current_predicate', 'current_predicate(dog)'):
        xfail('current_predicate/1 is not implemented', UncaughtError),
    ('current_predicate', 'current_predicate(0/dog)'):
        xfail('current_predicate/1 is not implemented', UncaughtError),
    ('current_prolog_flag', 'current_prolog_flag(debug, off)'):
        xfail('current_prolog_flag/2 is not implemented', UncaughtError),
    ('current_prolog_flag', '(set_prolog_flag(unknown, warning), current_prolog_flag(unknown, warning))'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('current_prolog_flag', '(set_prolog_flag(unknown, warning), current_prolog_flag(unknown, error))'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('current_prolog_flag', 'current_prolog_flag(debug, V)'):
        xfail('current_prolog_flag/2 is not implemented', UncaughtError),
    ('current_prolog_flag', 'current_prolog_flag(5, V)'):
        xfail('current_prolog_flag/2 is not implemented', UncaughtError),
    ('current_prolog_flag', 'current_prolog_flag(warning, V)'):
        xfail('current_prolog_flag/2 is not implemented', UncaughtError),
    ('fail', '(set_prolog_flag(unknown, fail), undef_pred)'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('fail', '(set_prolog_flag(unknown, warning), undef_pred)'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('file_manip', '(seek(my_file,3),at(my_file,X))'):
        skip('Requires the original INRIA file fixture and in/1 protocol'),
    ('file_manip', '(seek(my_file,eof),at(my_file,X))'):
        skip('Requires the original INRIA file fixture and in/1 protocol'),
    ('file_manip', '(seek(my_file,3),get_char(X,my_file))'):
        skip('Requires the original INRIA file fixture and in/1 protocol'),
    ('functor', '(current_prolog_flag(max_arity,A), X is A + 1, functor(T, foo, X))'):
        xfail('current_prolog_flag/2 is not implemented', UncaughtError),
    ('functor-bis', '(current_prolog_flag(max_arity,A), X is A + 1, functor(T, foo, X))'):
        xfail('current_prolog_flag/2 is not implemented', UncaughtError),
    ('halt', 'halt'):
        skip('Process termination needs a subprocess test, not this engine runner'),
    ('halt', 'halt(1)'):
        skip('Process termination needs a subprocess test, not this engine runner'),
    ('halt', 'halt(a)'):
        xfail('halt/1 is not implemented', UncaughtError),
    ('number_chars', "number_chars(A,['0',x,f])"):
        xfail('number_chars/2 does not parse hexadecimal notation', UncaughtError),
    ('number_chars', "number_chars(A,['0','''','A'])"):
        xfail('Parser does not support doubled quotes in quoted atoms', PrologParseError),
    ('number_codes', 'number_codes(33,L)'):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('number_codes', "number_codes(33,[0'3,0'3])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('number_codes', "number_codes(33.0,[0'3,0'.,0'3,0'E,0'+,0'0,0'1])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('number_codes', "number_codes(A,[0'-,0'2,0'5])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('number_codes', "number_codes(A,[0' ,0'3])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('number_codes', "number_codes(A,[0'0,0'x,0'f])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('number_codes', "number_codes(A,[0'0,39,0'a])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('number_codes', "number_codes(A,[0'4,0'.,0'2])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('number_codes', "number_codes(A,[0'4,0'2,0'.,0'0,0'e,0'-,0'1])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('number_codes', "number_codes(A,[ 0'1, 0'2, 1000])"):
        xfail("Parser does not support 0' character-code syntax", PrologParseError),
    ('set_prolog_flag', '(set_prolog_flag(unknown, fail), current_prolog_flag(unknown, V))'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('set_prolog_flag', 'set_prolog_flag(X, warning)'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('set_prolog_flag', 'set_prolog_flag(5, decimals)'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('set_prolog_flag', "set_prolog_flag(date, 'July 1999')"):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('set_prolog_flag', 'set_prolog_flag(debug, no)'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('set_prolog_flag', 'set_prolog_flag(max_arity, 40)'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('set_prolog_flag', 'setup(set_prolog_flag(double_quotes, atom)), X = "fred"'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('set_prolog_flag', 'setup(set_prolog_flag(double_quotes, codes)), X = "fred"'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('set_prolog_flag', 'setup(set_prolog_flag(double_quotes, chars)), X = "fred"'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('setof', 'setof(X,(X=1;X=2),L)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('setof', 'setof(X,(X=1;X=2),X)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('setof', 'setof(X,(X=2;X=1),L)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('setof', 'setof(X,(X=2;X=2),L)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('setof', 'setof(X,fail,L)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('setof', 'setof(1,(Y=2;Y=1),L)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('setof', 'setof(f(X,Y),(X=a;Y=b),L)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('setof', 'setof(X,Y^((X=1,Y=1);(X=2,Y=2)),S)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('setof', 'setof(X,Y^((X=1;Y=1);(X=2,Y=2)),S)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('setof', '(set_prolog_flag(unknown, warning), setof(X,(Y^(X=1;Y=1);X=3),S))'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('setof', '(set_prolog_flag(unknown, warning), setof(X,Y^(X=1;Y=1;X=3),S))'):
        xfail('set_prolog_flag/2 is not implemented', UncaughtError),
    ('setof', 'setof(X,(X=Y;X=Z;Y=1),L)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('setof', 'setof(X, X^(true; 4),L)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('setof', 'setof(X,1,L)'):
        xfail('setof/3 is not implemented', UncaughtError),
    ('sub_atom', 'sub_atom(abracadabra, 0, 5, _, S2)'):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', 'sub_atom(abracadabra, _, 5, 0, S2)'):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', 'sub_atom(abracadabra, 3, Length, 3, S2)'):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', 'sub_atom(abracadabra, Before, 2, After, ab)'):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', "sub_atom('Banana', 3, 2, _, S2)"):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', "sub_atom('charity', _, 3, _, S2)"):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', "sub_atom('ab', Before, Length, After, Sub_atom)"):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', 'sub_atom(Banana, 3, 2, _, S2)'):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', 'sub_atom(f(a), 2, 2, _, S2)'):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', "sub_atom('Banana', 4, 2, _, 2)"):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', "sub_atom('Banana', a, 2, _, S2)"):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', "sub_atom('Banana', 4, n, _, S2)"):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('sub_atom', "sub_atom('Banana', 4, _, m, S2)"):
        xfail('sub_atom/5 implementation is not registered as a builtin', UncaughtError),
    ('t', 'bagof([X,Y], t_foo(X,Y), S)'):
        skip('Requires the original INRIA t_foo fixture'),
}
