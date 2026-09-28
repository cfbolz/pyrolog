:- module(system, [term_expand/2, mode/1, (dynamic)/1]).

:- use_module(list).
:- use_module(dcg).
:- use_module(numbervars).
:- use_module(structural_comparison).
:- use_module(attvars).
:- use_module(freeze).
:- use_module(when).
:- use_module(coroutines).

% Accept advisory mode declarations without using them for optimization.
mode(_).

% User predicates already permit runtime modification without a declaration.
dynamic(_).

term_expand(A, A) :-
	A \= (_X --> _Y).

term_expand(A, B) :-
	A = (_X --> _Y),
	trans(A, B).
