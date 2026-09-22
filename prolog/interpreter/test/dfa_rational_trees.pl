% From CF Bolz-Tereick's "DFA Minimization using Rational Trees in Prolog":
% https://cfbolz.de/posts/dfa-minimization-using-rational-trees-in-prolog/
% Portability change: DOT strings are quoted atoms.

dfa_a_plus(S1) :-
    S1 = state(false, S2, none),
    S2 = state(true, S2, none).

dfa_a_plus_inefficient(S1) :-
    S1 = state(false, S2, none),
    S2 = state(true, S3, none),
    S3 = state(true, S4, none),
    S4 = state(true, S2, none).

match([], state(true, _, _)).
match([a | Rest], state(_, StateA, _)) :- match(Rest, StateA).
match([b | Rest], state(_, _, StateB)) :- match(Rest, StateB).

dfa_blog_post(S1) :-
    S1 = state(false, S2, S3),
    S2 = state(false, S4, S3),
    S3 = state(false, S5, S3),
    S4 = state(true, S5, S4),
    S5 = state(true, S4, S4).

number_states(D, L) :-
    number_states_helper(D, 0, _, [], LRev),
    reverse(LRev, L).

number_states_helper(none, Num, Num, L, L).
number_states_helper(State, Num, Num, L, L) :-
    member(State/_, L).
number_states_helper(State, NumIn, NumOut, LIn, LOut) :-
    not(member(State/_, LIn)),
    L1 = [State/NumIn | LIn],
    State = state(_, NextStateA, NextStateB),
    succ(NumIn, Num1),
    number_states_helper(NextStateA, Num1, Num2, L1, L2),
    number_states_helper(NextStateB, Num2, NumOut, L2, LOut).

to_dot(D) :-
    number_states(D, L),
    write('digraph G {'), nl,
    write('start [label="", shape=none]'), nl,
    write('start -> 0'), nl,
    to_dot_list(L, L),
    write('}'), nl.

to_dot_list([], _).
to_dot_list([State/NumState | Rest], FullList) :-
    State = state(Accept, StateA, StateB),
    to_dot_node(Accept, NumState),
    to_dot_edge(StateA, NumState, FullList, a),
    to_dot_edge(StateB, NumState, FullList, b),
    to_dot_list(Rest, FullList).

to_dot_node(true, Num) :-
    write(Num), write(' [shape=doublecircle]'), nl.
to_dot_node(false, Num) :-
    write(Num), write(' [shape=circle]'), nl.

to_dot_edge(none, _, _, _).
to_dot_edge(State, NumPrev, FullList, Char) :-
    member(State/NumState, FullList),
    write(NumPrev), write(' -> '), write(NumState),
    write(' [label='), write(Char), write(']'), nl.
