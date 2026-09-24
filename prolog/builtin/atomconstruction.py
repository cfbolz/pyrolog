from prolog.interpreter import helper, term, error
from prolog.interpreter import continuation
from prolog.builtin.register import expose_builtin
from prolog.interpreter.term import specialized_term_classes
from prolog.interpreter.term import Callable
import re
import sys
from rpython.rlib import rutf8, rstring

# ___________________________________________________________________
# analysing and construction atoms

@continuation.make_failure_continuation
def continue_atom_concat(Choice, engine, scont, fcont, heap, var1, var2, result, i):
    if i < len(result):
        fcont = Choice(engine, scont, fcont, heap, var1, var2, result,
                       rutf8.next_codepoint_pos(result, i))
        heap = heap.branch()
    var1.unify(term.Callable.build(result[:i], cache=False), heap)
    var2.unify(term.Callable.build(result[i:], cache=False), heap)
    return scont, fcont, heap

@expose_builtin("atom_concat", unwrap_spec=["obj", "obj", "obj"], handles_continuation=True)
def impl_atom_concat(engine, heap, a1, a2, result, scont, fcont):
    if isinstance(a1, term.Var):
        r = helper.convert_to_str(result)
        if isinstance(a2, term.Var):
            return continue_atom_concat(engine, scont, fcont, heap, a1, a2, r, 0)
        else:
            s2 = helper.convert_to_str(a2)
            if r.endswith(s2):
                stop = len(r) - len(s2)
                assert stop >= 0
                a1.unify(term.Callable.build(r[:stop], cache=False), heap)
            else:
                raise error.UnificationFailed()
    else:
        s1 = helper.convert_to_str(a1)
        if isinstance(a2, term.Var):
            r = helper.convert_to_str(result)
            if r.startswith(s1):
                a2.unify(term.Callable.build(r[len(s1):], cache=False), heap)
            else:
                raise error.UnificationFailed()
        else:
            s2 = helper.convert_to_str(a2)
            result.unify(term.Callable.build(s1 + s2, cache=False), heap)
    return scont, fcont, heap

@expose_builtin("atom_length", unwrap_spec=["obj", "obj"])
def impl_atom_length(engine, heap, atom, length):
    if isinstance(atom, term.Var):
        error.throw_instantiation_error()
    if not isinstance(atom, term.Atom):
        error.throw_type_error('atom', atom)
    sub_atom_index(length)
    term.Number(atom.signature().name_length).unify(length, heap)



def sub_atom_index(value):
    if isinstance(value, term.Var):
        return -1
    if isinstance(value, term.BigInt):
        if value.value.get_sign() < 0:
            error.throw_domain_error('not_less_than_zero', value)
        try:
            return value.value.toint()
        except OverflowError:
            # An offset larger than any byte string cannot match.
            return sys.maxint
    if not isinstance(value, term.Number):
        error.throw_type_error('integer', value)
    result = value.num
    if result < 0:
        error.throw_domain_error("not_less_than_zero", value)
    return result


def advance_codepoints(text, pos, count):
    for unused in range(count):
        pos = rutf8.next_codepoint_pos(text, pos)
    return pos


@continuation.make_failure_continuation
def continue_sub_atom(Choice, engine, scont, fcont, heap, text, size,
                      before, length, after, sub, b, l, start, stop,
                      last_b, wanted_l, wanted_a):
    while b <= last_b:
        current_b, current_l = b, l
        current_start, current_stop = start, stop
        # Save the next candidate's character indices and byte cursors before
        # unification. Backtracking resumes directly at that candidate.
        if wanted_l >= 0 or wanted_a >= 0 or l == size - b:
            b += 1
            if b <= last_b:
                start = rutf8.next_codepoint_pos(text, start)
                if wanted_l >= 0:
                    stop = rutf8.next_codepoint_pos(text, stop)
                elif wanted_a >= 0:
                    l = size - b - wanted_a
                else:
                    l = 0
                    stop = start
        else:
            l += 1
            stop = rutf8.next_codepoint_pos(text, stop)
        if isinstance(sub, term.Atom):
            if not rstring.startswith(text, sub.name(), current_start, len(text)):
                continue
            part = sub
        else:
            assert 0 <= current_start <= current_stop
            part = Callable.build(text[current_start:current_stop], cache=False)
        undoheap = heap
        heap = heap.branch()
        try:
            before.unify(term.Number(current_b), heap)
            length.unify(term.Number(current_l), heap)
            after.unify(term.Number(size - current_b - current_l), heap)
            sub.unify(part, heap)
        except error.UnificationFailed:
            heap = heap.revert_upto(undoheap, discard_choicepoint=True)
            continue
        if b <= last_b:
            fcont = Choice(engine, scont, fcont, undoheap, text, size,
                           before, length, after, sub, b, l, start, stop,
                           last_b, wanted_l, wanted_a)
        return scont, fcont, heap
    return fcont.fail(heap)


@expose_builtin("sub_atom", unwrap_spec=["obj", "obj", "obj", "obj", "obj"],
                handles_continuation=True)
def impl_sub_atom(engine, heap, atom, before, length, after, sub, scont, fcont):
    if isinstance(atom, term.Var):
        error.throw_instantiation_error()
    text = helper.unwrap_atom(atom)
    assert isinstance(atom, term.Atom)
    size = atom.signature().name_length
    b = sub_atom_index(before)
    l = sub_atom_index(length)
    a = sub_atom_index(after)
    if not isinstance(sub, term.Var) and not isinstance(sub, term.Atom):
        error.throw_type_error("atom", sub)
    if isinstance(sub, term.Atom):
        sub_length = sub.signature().name_length
        if l >= 0 and l != sub_length:
            return fcont.fail(heap)
        l = sub_length
    if b > size or l > size or a > size:
        return fcont.fail(heap)
    # Derive a missing index from Before + Length + After = Total. Use
    # subtraction so oversized, but machine-sized, inputs cannot overflow.
    if b >= 0 and l >= 0:
        remaining = size - b - l
        if remaining < 0 or (a >= 0 and a != remaining):
            return fcont.fail(heap)
        a = remaining
    elif b >= 0 and a >= 0:
        l = size - b - a
        if l < 0:
            return fcont.fail(heap)
    elif l >= 0 and a >= 0:
        b = size - l - a
        if b < 0:
            return fcont.fail(heap)
    if b >= 0:
        last_b = b
    elif l >= 0:
        last_b = size - l
    elif a >= 0:
        last_b = size - a
    else:
        last_b = size
    b = max(0, b)
    current_l = l if l >= 0 else (size - b - a if a >= 0 else 0)
    start = advance_codepoints(text, 0, b)
    stop = advance_codepoints(text, start, current_l)
    return continue_sub_atom(engine, scont, fcont, heap, text, size,
                             before, length, after, sub, b, current_l,
                             start, stop, last_b, l, a)


def atom_to_cons(atom, codes=False):
    if codes:
        charlist = [term.Number(c) for c in rutf8.Utf8StringIterator(atom.name())]
    else:
        charlist = [term.Callable.build(rutf8.unichr_as_utf8(c))
                    for c in rutf8.Utf8StringIterator(atom.name())]
    return helper.wrap_list(charlist)
        
def cons_to_atom(cons, codes=False):
    result = helper.unwrap_char_list(cons, codes=codes)
    return Callable.build("".join(result))

@expose_builtin("atom_chars", unwrap_spec=["obj", "obj"])
def impl_atom_chars(engine, heap, atom, charlist):
    atom_convert(heap, atom, charlist)


@expose_builtin("atom_codes", unwrap_spec=["obj", "obj"])
def impl_atom_codes(engine, heap, atom, codelist):
    atom_convert(heap, atom, codelist, codes=True)


def atom_convert(heap, atom, charlist, codes=False):
    if not isinstance(atom, term.Atom) and not isinstance(atom, term.Var):
        error.throw_type_error("atom", atom)
    if not isinstance(charlist, term.Var):  
        if isinstance(atom, term.Atom):
            helper.unwrap_char_list(charlist, allow_partial=True, codes=codes)
            atom_to_cons(atom, codes=codes).unify(charlist, heap)
        else:
            cons_to_atom(charlist, codes=codes).unify(atom, heap)
    else:
        if isinstance(atom, term.Var):
            error.throw_instantiation_error()
        elif not isinstance(atom, term.Atom):
            error.throw_type_error("atom", atom)
        else:
            atom_to_cons(atom, codes=codes).unify(charlist, heap)


@expose_builtin("char_code", unwrap_spec=["obj", "obj"])
def impl_char_code(engine, heap, char, code):
    if isinstance(char, term.Var):
        char.unify(Callable.build(helper.unwrap_char_code(code)), heap)
    else:
        if not isinstance(char, term.Atom) or char.signature().name_length != 1:
            error.throw_type_error("character", char)
        if not isinstance(code, term.Var):
            helper.unwrap_char_code(code)
        code.unify(term.Number(rutf8.codepoint_at_pos(char.name(), 0)), heap)
