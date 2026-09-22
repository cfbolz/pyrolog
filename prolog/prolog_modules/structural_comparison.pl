:- module(structural_comparison, ['?='/2]).

'?='(X, Y) :- \+ unifiable(X, Y, [_|_]).
