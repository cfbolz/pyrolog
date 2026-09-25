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


@pytest.mark.parametrize('jit_options', ['off', 'threshold=40'])
def test_module_operators(tmpdir, jit_options):
    source = """
        :- module(left, []).
        :- op(450, xfy, joins).
        chain(a joins b joins c).
        read_it(S,T) :- read(S,T).
        write_it(S,T) :- write_term(S,T,[]).
        :- module(right, []).
        :- op(350, yfx, joins).
    """
    path = tmpdir.join('operators.pl')
    query = (
        "left:chain(joins(a,joins(b,c))), "
        "T = a joins b joins c, T = joins(joins(a,b),c), "
        "findall(F,left:current_op(_,F,joins),[xfy]), "
        "open('%s',write,W), left:write_it(W,joins(a,b)), "
        "put_char(W,'.'), close(W), open('%s',read,R), "
        "left:read_it(R,joins(a,b)), close(R), "
        "op(0,xfy,left:joins), \\+ left:current_op(_,_,joins), "
        "current_op(350,yfx,joins), write(operators_passed), nl.\n" % (path,path))
    log = run_log(tmpdir, source, query, jit_options)
    assert 'operators_passed\n' in log.result


@pytest.mark.parametrize('jit_options', ['off', 'threshold=40'])
def test_exported_operators(tmpdir, jit_options):
    library = tmpdir.join('relations.pl')
    library.write('''
        :- module(relations, [op(500,xfx,likes), pair/1]).
        pair(alice likes bob).
    ''')
    source = """
        :- module(client, []).
        :- use_module('%s', [op(_,_,likes), pair/1]).
        example(alice likes bob).
    """ % library
    query = (
        "pair(X), example(X), X == likes(alice,bob), "
        "\\+ current_op(_,_,user:likes), "
        "use_module('%s', [op(500,xfx,likes)]), "
        "op(700,xfy,relations:likes), current_op(500,xfx,likes), "
        "write(operator_exports_passed), nl.\n" % library)
    log = run_log(tmpdir, source, query, jit_options)
    assert 'operator_exports_passed\n' in log.result
