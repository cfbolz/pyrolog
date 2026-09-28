:- module(sort, [sort/2]).
:- use_module(list, [length/2]).

sort(List, Sorted) :-
    ( is_list(List) -> length(List, Length)
    ; list_error(List, List, 1, 1, List)
    ),
    sort_n(Length, List, [], Result),
    Sorted = Result.

% Distinguish open lists from malformed or cyclic spines without binding them.
% Only invalid inputs reach this traversal. Checkpoints move at doubling
% intervals so a cyclic spine is detected without inspecting its elements.
list_error(Tail, _, _, _, _) :-
    var(Tail),
    throw(error(instantiation_error)).
list_error([_|Tail], Checkpoint, Power, Remaining, List) :-
    ( Tail == Checkpoint ->
        throw(error(type_error(list, List)))
    ; Remaining =:= 1 ->
        Power1 is Power * 2,
        list_error(Tail, Tail, Power1, Power1, List)
    ; Remaining1 is Remaining - 1,
      list_error(Tail, Checkpoint, Power, Remaining1, List)
    ).
list_error(_, _, _, _, List) :-
    throw(error(type_error(list, List))).

% Consume N elements, returning the unused suffix and a sorted unique list.
sort_n(0, Rest, Rest, []) :- !.
sort_n(1, [X|Rest], Rest, [X]) :- !.
sort_n(N, List, Rest, Sorted) :-
    LeftN is N // 2,
    RightN is N - LeftN,
    sort_n(LeftN, List, Middle, Left),
    sort_n(RightN, Middle, Rest, Right),
    merge(Left, Right, Sorted).

merge([], Right, Right) :- !.
merge(Left, [], Left).
merge([X|Xs], [Y|Ys], Sorted) :-
    compare(Order, X, Y),
    merge_order(Order, X, Xs, Y, Ys, Sorted).

merge_order('<', X, Xs, Y, Ys, [X|Rest]) :-
    merge(Xs, [Y|Ys], Rest).
merge_order('>', X, Xs, Y, Ys, [Y|Rest]) :-
    merge([X|Xs], Ys, Rest).
merge_order('=', X, Xs, _, Ys, [X|Rest]) :-
    merge(Xs, Ys, Rest).
