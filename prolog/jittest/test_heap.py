from prolog.jittest.support import BaseTestPyrologC


class TestHeap(BaseTestPyrologC):
    def test_nested_cuts_keep_retained_heap_undo_records(self):
        log = self.run_and_check('''
            inner(X,V) :- X=a, V=f(_), (true;true), catch(true,_,true), !.
            middle(X,Y,V) :- Y=b, (true;true), inner(X,V), !.
            outer(X,Y,Z,V) :- Z=c, (true;true), middle(X,Y,V), !,
                             V=f(W), W=d.
            check :- (outer(X,Y,Z,V), fail ;
                      var(X), var(Y), var(Z), var(V)).
            loop(0) :- !.
            loop(N) :- check, M is N - 1, loop(M).
        ''', 'loop(1000).')
        assert 'yes' in log.result
