"""Round trips across UTF-8 storage, code lists and quoted source."""
from hypothesis import given, settings, strategies as st
from prolog.interpreter.term import Callable
from prolog.interpreter.parsing import get_engine, parse_query_term
from prolog.interpreter.helper import unwrap_list
from prolog.builtin.atomconstruction import atom_to_cons, cons_to_atom
from prolog.builtin.formatting import TermFormatter


@settings(max_examples=100, deadline=None)
@given(st.text(alphabet=st.characters(blacklist_categories=('Cs',)), max_size=20))
def test_unicode_roundtrips(value):
    raw = value.encode('utf-8')
    atom = Callable.build(raw)
    codes = atom_to_cons(atom, codes=True)
    assert [n.num for n in unwrap_list(codes)] == [ord(c) for c in value]
    assert cons_to_atom(codes, codes=True).name() == raw
    assert cons_to_atom(atom_to_cons(atom)).name() == raw
    rendered = TermFormatter(get_engine(''), quoted=True).format(atom)
    assert parse_query_term(rendered + ' .').name() == raw
