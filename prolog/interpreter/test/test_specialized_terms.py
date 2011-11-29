from prolog.interpreter.term import Atom, Number, Term, Callable, specialized_term_classes
from prolog.interpreter.test.tool import parse
from prolog.interpreter import signature
import py

    
def test_callable_build_for_term1():
    t1 = parse('t(a).')[0]
    assert not isinstance(t1, Term)
    assert isinstance(t1, Callable)
    assert t1.name() == 't'
    assert t1.signature().string() == 't/1'
    assert len(t1.arguments()) == 1
    assert t1.arguments()[0] is not None
    assert t1.argument_at(0).name() == 'a'
    assert t1.argument_count() == 1

def test_callable_build_for_term1_from_factory():
    t2 = Callable.build('foo', [Atom('bar')])
    assert not isinstance(t2, Term)
    assert isinstance(t2, Callable)
    assert t2.name() == 'foo'
    assert t2.signature().string() == 'foo/1'
    assert len(t2.arguments()) == 1
    assert t2.arguments()[0] is not None
    assert t2.argument_at(0).name() == 'bar'
    assert t2.argument_count() == 1

def test_dont_cache_atoms():
    a1 = Callable.build('foo', cache=False)
    a2 = Callable.build('foo', cache=False)
    assert a1 is not a2
    a1 = Callable.build('foo')
    a2 = Callable.build('foo')
    assert a1 is a2

# ___________________________________________________________________
# tests for term specialization

from prolog.interpreter import specialterm

def test_specialize_on_build():
    sig = signature.Signature.getsignature("foo", 1)
    a1 = specialterm.SpecialTerm(sig, [Number(0)])
    assert isinstance(a1, specialterm.SpecialTerm)
    s1 = a1.get_shape()
    a2 = specialterm.SpecialTerm(sig, [Callable.build("blubl")])
    assert isinstance(a1, specialterm.SpecialTerm)
    s2 = a2.get_shape()
    assert s1 is not s2
    a3 = specialterm.SpecialTerm(sig, [Number(1)])
    assert a3.get_shape() is s1
