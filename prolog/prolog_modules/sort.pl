:- module(sort, [sort/2, sort/4, keysort/2]).
:- use_module(list, [length/2]).

sort(List, Sorted) :-
    sort(0, @<, List, Sorted).

sort(Key, Order, List, Sorted) :-
    check_key(Key),
    sort_order(Order, Direction, Duplicates),
    list_length(List, Length),
    decorate(Key, List, Decorated),
    sort_n(Length, Decorated, [], Key, Direction, Duplicates, Ordered),
    undecorate(Key, Ordered, Result),
    Sorted = Result.

keysort(List, Sorted) :-
    list_length(List, _),
    check_pairs(List),
    sort(1, @=<, List, Sorted).

check_pairs([]).
check_pairs([Pair|Rest]) :-
    ( var(Pair) -> throw(error(instantiation_error))
    ; Pair = _-_ -> check_pairs(Rest)
    ; throw(error(type_error(pair, Pair)))
    ).

% Integer keys select arguments; a list of positive keys selects a path.
check_key(Key) :-
    ( var(Key) -> throw(error(instantiation_error))
    ; integer(Key) ->
        ( Key >= 0 -> true
        ; throw(error(domain_error(not_less_than_one, Key)))
        )
    ; is_list(Key), Key \== [] -> check_path(Key)
    ; throw(error(type_error(sort_key, Key)))
    ).

check_path([]).
check_path([Key|Rest]) :-
    ( var(Key) -> throw(error(instantiation_error))
    ; integer(Key) ->
        ( Key > 0 -> true
        ; throw(error(domain_error(not_less_than_one, Key)))
        )
    ; throw(error(type_error(sort_key, Key)))
    ),
    check_path(Rest).

sort_order(Order, Direction, Duplicates) :-
    ( var(Order) -> throw(error(instantiation_error))
    ; atom(Order) ->
        ( order_options(Order, Direction, Duplicates) -> true
        ; throw(error(domain_error(order, Order)))
        )
    ; throw(error(type_error(atom, Order)))
    ).

order_options('@<', '<', remove).
order_options('<', '<', remove).
order_options('@=<', '<', keep).
order_options('=<', '<', keep).
order_options('@>', '>', remove).
order_options('>', '>', remove).
order_options('@>=', '>', keep).
order_options('>=', '>', keep).

list_length(List, Length) :-
    ( is_list(List) -> length(List, Length)
    ; list_error(List, List, 1, 1, List)
    ).

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

% Whole-term sorting needs neither wrappers nor an extra list traversal.
decorate(Key, List, Decorated) :-
    ( Key == 0 -> Decorated = List
    ; decorate_keys(Key, List, Decorated)
    ).

decorate_keys(_, [], []).
decorate_keys(Key, [X|Xs], [Value-X|Rest]) :-
    extract_key(Key, X, Value),
    decorate_keys(Key, Xs, Rest).

% Extract keys once, including for singleton lists which need no comparisons.
extract_key(Key, Term, Value) :-
    ( integer(Key) -> key_argument(Key, Term, Value)
    ; extract_path(Key, Term, Value)
    ).

extract_path([], Term, Term).
extract_path([Key|Rest], Term, Value) :-
    key_argument(Key, Term, Argument),
    extract_path(Rest, Argument, Value).

key_argument(Key, Term, Value) :-
    ( var(Term) -> throw(error(instantiation_error))
    ; compound(Term) ->
        functor(Term, _, Arity),
        ( Key =< Arity -> arg(Key, Term, Value)
        ; throw(error(existence_error(argument, Key, Term)))
        )
    ; throw(error(type_error(compound, Term)))
    ).

% Consume contiguous halves so equal keys retain their original order.
sort_n(0, Rest, Rest, _, _, _, []) :- !.
sort_n(1, [X|Rest], Rest, _, _, _, [X]) :- !.
sort_n(N, List, Rest, Key, Direction, Duplicates, Sorted) :-
    LeftN is N // 2,
    RightN is N - LeftN,
    sort_n(LeftN, List, Middle, Key, Direction, Duplicates, Left),
    sort_n(RightN, Middle, Rest, Key, Direction, Duplicates, Right),
    merge(Left, Right, Key, Direction, Duplicates, Sorted).

merge([], Right, _, _, _, Right) :- !.
merge(Left, [], _, _, _, Left).
merge([X|Xs], [Y|Ys], Key, Direction, Duplicates, Sorted) :-
    ( Key == 0 -> compare(Order, X, Y)
    ; X = KX-_, Y = KY-_, compare(Order, KX, KY)
    ),
    ( Order == '=' ->
        Sorted = [X|Rest],
        ( Duplicates == remove ->
            merge(Xs, Ys, Key, Direction, Duplicates, Rest)
        ; merge(Xs, [Y|Ys], Key, Direction, Duplicates, Rest)
        )
    ; Order == Direction ->
        Sorted = [X|Rest],
        merge(Xs, [Y|Ys], Key, Direction, Duplicates, Rest)
    ; Sorted = [Y|Rest],
      merge([X|Xs], Ys, Key, Direction, Duplicates, Rest)
    ).

undecorate(Key, List, Undecorated) :-
    ( Key == 0 -> Undecorated = List
    ; undecorate_keys(List, Undecorated)
    ).

undecorate_keys([], []).
undecorate_keys([_-X|Rest], [X|Xs]) :-
    undecorate_keys(Rest, Xs).
