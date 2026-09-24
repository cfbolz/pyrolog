# coding: utf-8
import pytest
from prolog.jittest.support import BaseTestPyrologC, run_log


class TestUnicode(BaseTestPyrologC):
    def test_unicode_atom_loop(self):
        source = """
            循环(0) :- !.
            循环(N) :-
                Code is 128512 + N mod 2,
                char_code(C, Code),
                atom_concat('é', C, A),
                atom_length(A, 2), atom_codes(A, [233, Code]),
                sub_atom(A, 1, 1, 0, C),
                Next is N - 1, 循环(Next).
        """
        log = self.run_and_check(source, '循环(400), write(unicode_passed), nl.')
        assert 'unicode_passed\n' in log.result


@pytest.mark.parametrize('jit_options', ['off', 'threshold=40'])
def test_unicode_streams_and_quoted_terms(tmpdir, jit_options):
    path = str(tmpdir.join('unicode.txt'))
    query = ("open('%s',write,S), put_code(S,128512), put_code(S,0), "
             "write_term(S,'é\\'😀',[quoted(true)]), put_char(S,'.'), close(S), "
             "open('%s',read,R), peek_char(R,'😀'), get_code(R,128512), "
             "get_code(R,0), read(R,'é\\'😀'), close(R), "
             "write(stream_passed), nl." % (path, path))
    log = run_log(tmpdir, '', query, jit_options)
    assert 'stream_passed\n' in log.result
