from prolog.interpreter import helper, term, error
from prolog.interpreter import continuation
from prolog.builtin.register import expose_builtin
from prolog.interpreter.term import specialized_term_classes
from prolog.interpreter.term import Callable
import re
import sys
from rpython.rlib import rutf8

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

@expose_builtin("atom_length", unwrap_spec = ["atom", "obj"])
def impl_atom_length(engine, heap, s, length):
    sub_atom_index(length)
    term.Number(rutf8.codepoints_in_utf8(s)).unify(length, heap)



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


@continuation.make_failure_continuation
def continue_sub_atom(Choice, engine, scont, fcont, heap, text, offsets,
                      before, length, after, sub, b, l, wanted_b, wanted_l,
                      wanted_a):
    size = len(offsets) - 1
    while b <= size:
        while l <= size - b:
            current_l = l
            l += 1
            if wanted_l >= 0 and current_l != wanted_l:
                continue
            a = size - b - current_l
            if wanted_a >= 0 and a != wanted_a:
                continue
            start = offsets[b]
            stop = offsets[b + current_l]
            assert 0 <= start <= stop
            part = text[start:stop]
            if isinstance(sub, term.Atom) and part != sub.name():
                continue
            undoheap = heap
            heap = heap.branch()
            try:
                before.unify(term.Number(b), heap)
                length.unify(term.Number(current_l), heap)
                after.unify(term.Number(a), heap)
                sub.unify(Callable.build(part, cache=False), heap)
            except error.UnificationFailed:
                heap = heap.revert_upto(undoheap, discard_choicepoint=True)
                continue
            fcont = Choice(engine, scont, fcont, undoheap, text, offsets,
                           before, length, after, sub, b, l, wanted_b,
                           wanted_l, wanted_a)
            return scont, fcont, heap
        if wanted_b >= 0:
            break
        b += 1
        l = 0
    return fcont.fail(heap)


@expose_builtin("sub_atom", unwrap_spec=["atom", "obj", "obj", "obj", "obj"],
                handles_continuation=True)
def impl_sub_atom(engine, heap, text, before, length, after, sub, scont, fcont):
    b = sub_atom_index(before)
    l = sub_atom_index(length)
    a = sub_atom_index(after)
    if not isinstance(sub, term.Var) and not isinstance(sub, term.Atom):
        error.throw_type_error("atom", sub)
    if b > len(text) or l > len(text) or a > len(text):
        return fcont.fail(heap)
    # Keep byte offsets separate from the code-point indices exposed to Prolog.
    offsets = [0]
    pos = 0
    while pos < len(text):
        pos = rutf8.next_codepoint_pos(text, pos)
        offsets.append(pos)
    return continue_sub_atom(engine, scont, fcont, heap, text, offsets,
                             before, length, after, sub, max(0, b), 0, b, l, a)


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
        if not isinstance(char, term.Atom) or rutf8.codepoints_in_utf8(char.name()) != 1:
            error.throw_type_error("character", char)
        if not isinstance(code, term.Var):
            helper.unwrap_char_code(code)
        code.unify(term.Number(rutf8.codepoint_at_pos(char.name(), 0)), heap)
