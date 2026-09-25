import pytest

from prolog.jittest.support import run_log


@pytest.mark.parametrize('jit_options', ['off', 'threshold=40'])
def test_parser_entry_points(tmpdir, jit_options):
    source = ('parsed(f((a,b)), -1, -(1), +1).\n'
              'relaxed(a :- b, [a;b|c;d]).')
    path = tmpdir.join('term.pl')
    path.write('f((a,b)). f (a).')
    comma_path = tmpdir.join('comma.pl')
    query = (
        "parsed(T,N,Minus,Plus), functor(T,f,1), N == -1, "
        "Minus =.. ['-',1], Plus =.. ['+',1], "
        "relaxed(Clause,[Head|Tail]), Clause =.. [':-',a,b], "
        "Head =.. [';',a,b], Tail =.. [';',c,d], "
        "Q = f((a,b)), Q == T, "
        "open('%s',read,S), read(S,T), "
        "catch(read(S,_),error(syntax_error(_)),Caught=yes), "
        "Caught == yes, close(S), "
        "open('%s',write,W), write_term(W,',',[quoted(true)]), "
        "put_char(W,'.'), close(W), "
        "open('%s',read,R), read(R,','), close(R), "
        "write(parser_passed), nl.\n" % (path, comma_path, comma_path))
    log = run_log(tmpdir, source, query, jit_options)
    assert 'parser_passed\n' in log.result
