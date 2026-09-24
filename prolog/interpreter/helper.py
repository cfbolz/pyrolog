""" Helper functions for dealing with prolog terms"""

from prolog.interpreter import term
from prolog.interpreter import error
from prolog.interpreter.signature import Signature
from rpython.rlib import jit
from prolog.interpreter.stream import PrologOutputStream, PrologInputStream,\
        PrologStream

conssig = Signature.getsignature(".", 2)
nilsig = Signature.getsignature("[]", 0)

emptylist = term.Callable.build("[]")


class ListSpineDetector(object):
    """Brent's cycle check, advanced alongside the consumer's traversal.

    Only dereferenced tails are compared: cycles in elements are irrelevant.
    The checkpoint moves after 1, 2, 4, ... steps, requiring constant space
    and no extra traversal or visited dictionary.
    """
    def __init__(self, root):
        self.checkpoint = root
        self.power = 1
        self.remaining = 1

    def advance(self, tail, root):
        if self.is_cycle(tail):
            error.throw_type_error("list", root)

    def is_cycle(self, tail):
        if tail is self.checkpoint:
            return True
        self.remaining -= 1
        if self.remaining == 0:
            self.checkpoint = tail
            self.power *= 2
            self.remaining = self.power
        return False


def list_spine_tail(root):
    """Return [] or the open/improper tail; a cons cell denotes a cycle.

    This is read-only, including for open lists and attributed variables.
    """
    curr = root.dereference(None)
    detector = ListSpineDetector(curr)
    while isinstance(curr, term.Callable) and curr.signature().eq(conssig):
        curr = curr.argument_at(1).dereference(None)
        if detector.is_cycle(curr):
            return curr
    return curr


def wrap_list(python_list):
    curr = emptylist
    for i in range(len(python_list) - 1, -1, -1):
        curr = term.Callable.build(".", [python_list[i], curr])
    return curr

@jit.unroll_safe
def unwrap_list(prolog_list):
    # Grrr, stupid JIT
    result = [None]
    used = 0
    curr = prolog_list.dereference(None)
    detector = ListSpineDetector(curr)
    while isinstance(curr, term.Callable) and curr.signature().eq(conssig):
        if used == len(result):
            nresult = [None] * (used * 2)
            for i in range(used):
                nresult[i] = result[i]
            result = nresult
        result[used] = curr.argument_at(0)
        used += 1
        curr = curr.argument_at(1)
        curr = curr.dereference(None)
        detector.advance(curr, prolog_list)
    if isinstance(curr, term.Callable) and curr.signature().eq(nilsig):
        if used != len(result):
            nresult = [None] * used
            for i in range(used):
                nresult[i] = result[i]
            result = nresult
        return result
    error.throw_type_error("list", prolog_list)

def unwrap_char_list(prolog_list, allow_partial=False, codes=False):
    """Validate a character list; return None for an allowed partial list."""
    result = []
    partial = False
    curr = prolog_list.dereference(None)
    detector = ListSpineDetector(curr)
    while isinstance(curr, term.Callable) and curr.signature().eq(conssig):
        char = curr.argument_at(0).dereference(None)
        if isinstance(char, term.Var):
            if not allow_partial:
                error.throw_instantiation_error()
            partial = True
        elif codes:
            result.append(unwrap_char_code(char))
        elif not isinstance(char, term.Atom) or len(char.name()) != 1:
            error.throw_type_error("character", char)
        else:
            result.append(char.name())
        curr = curr.argument_at(1).dereference(None)
        detector.advance(curr, prolog_list)
    if isinstance(curr, term.Var):
        if not allow_partial:
            error.throw_instantiation_error()
        partial = True
    elif not isinstance(curr, term.Callable) or not curr.signature().eq(nilsig):
        error.throw_type_error("list", prolog_list)
    if partial:
        return None
    return result


def unwrap_char_code(obj):
    """Convert a code to a byte character; atom signatures exclude NUL."""
    if isinstance(obj, term.Var):
        error.throw_instantiation_error()
    if isinstance(obj, term.Number):
        code = obj.num
    elif isinstance(obj, term.BigInt):
        try:
            code = obj.value.toint()
        except OverflowError:
            raise error.throw_representation_error("character_code")
    else:
        raise error.throw_type_error("integer", obj)
    if code <= 0 or code > 255:
        error.throw_representation_error("character_code")
    return chr(code)


def is_callable(var, engine):
    return isinstance(var, term.Callable)

def ensure_callable(var):
    if isinstance(var, term.Var):
        error.throw_instantiation_error()
    elif isinstance(var, term.Callable):
        return var
    else:
        error.throw_type_error("callable", var)

def unwrap_int(obj):
    if isinstance(obj, term.Number):
        return obj.num
    elif isinstance(obj, term.Float):
        f = obj.floatval; i = int(f)
        if f == i:
            return i
    elif isinstance(obj, term.Var):
        error.throw_instantiation_error()
    error.throw_type_error('integer', obj)

def unwrap_atom(obj):
    if isinstance(obj, term.Atom):
        return obj.name()    
    error.throw_type_error('atom', obj)

def unwrap_predicate_indicator(predicate):
    predicate = predicate.dereference(None)
    if not isinstance(predicate, term.Callable):
        error.throw_type_error("predicate_indicator", predicate)
        assert 0, "unreachable"
    if not predicate.name()== "/" or predicate.argument_count() != 2:
        error.throw_type_error("predicate_indicator", predicate)
    name = unwrap_atom(predicate.argument_at(0).dereference(None))
    arity = unwrap_int(predicate.argument_at(1).dereference(None))
    return name, arity

def unwrap_stream(engine, obj):
    if isinstance(obj, term.Var):
        error.throw_instantiation_error()
    if isinstance(obj, term.Atom):
        try:
            stream = engine.streamwrapper.aliases[obj.name()]
        except KeyError:
            pass
        else:
            assert isinstance(stream, PrologStream)
            return stream
    error.throw_domain_error("stream", obj)

def unwrap_instream(engine, obj):
    if isinstance(obj, term.Var):
        error.throw_instantiation_error()
    if isinstance(obj, term.Atom):
        try:
            stream = engine.streamwrapper.aliases[obj.name()]
        except KeyError:
            pass
        else:
            if not isinstance(stream, PrologInputStream):
                error.throw_permission_error("input", "stream",
                        term.Atom(stream.alias))
            assert isinstance(stream, PrologInputStream)
            return stream
    error.throw_domain_error("stream", obj)

def unwrap_outstream(engine, obj):
    if isinstance(obj, term.Var):
        error.throw_instantiation_error()
    if isinstance(obj, term.Atom):
        try:
            stream = engine.streamwrapper.aliases[obj.name()]
        except KeyError:
            pass
        else:
            if not isinstance(stream, PrologOutputStream):
                error.throw_permission_error("output", "stream",
                        term.Atom(stream.alias))
            assert isinstance(stream, PrologOutputStream)
            return stream
    error.throw_domain_error("stream", obj)

def ensure_atomic(obj):
    if not is_atomic(obj):
        error.throw_type_error('atomic', obj)
    return obj

def is_atomic(obj):
    return (isinstance(obj, term.Atom) or isinstance(obj, term.Float) or 
            isinstance(obj, term.Number))

def is_term(obj):
    return isinstance(obj, term.Callable) and obj.argument_count() > 0

def convert_to_str(obj):
    if isinstance(obj, term.Var):
        error.throw_instantiation_error()
    if isinstance(obj, term.Atom):
        return obj.name()    
    elif isinstance(obj, term.Number):
        return str(obj.num)
    elif isinstance(obj, term.Float):
        return str(obj.floatval)
    elif isinstance(obj, term.BigInt):
        return obj.value.str()
    error.throw_type_error("atom", obj)

def is_numeric(obj):
    return isinstance(obj, term.Number) or isinstance(obj, term.BigInt)\
            or isinstance(obj, term.Float)
