:- module(when, []).

% Keep the public condition and qualified goal shared by all callbacks of one
% suspension. State also lets projection suppress duplicate and spent goals.
run_suspension(_, Goal, State) :-
    (var(State) -> State = done, call(Goal) ; true).

% This module is loaded before system:term_expand/2 is available, so spell
% out the two DCG arguments during bootstrap.
attribute_goals(X, S0, S) :-
    get_attr(X, when, Goals),
    residual_goals(X, Goals, S0, S).

residual_goals(X, (A,B), S0, S) :- !,
    residual_goals(X, A, S0, S1),
    residual_goals(X, B, S1, S).
residual_goals(X, Callback, S0, S) :-
    (suspension(Callback, Cond, Goal, State) ->
        (var(State) ->
            % copy_term/3 rolls this binding back after copying the goals.
            State = projected,
            S0 = [coroutines:when(Cond, Goal)|S]
        ; S0 = S
        )
    ;
        % Other coroutines (currently dif/2) also use this attribute module.
        % Reinstall each callback by appending, not by overwriting its peers.
        S0 = [coroutines:put_when_attributes([X], Callback)|S]
    ).

suspension(when:run_suspension(Cond, Goal, State), Cond, Goal, State).
suspension(coroutines:when_impl(_, Next), Cond, Goal, State) :-
    suspension(Next, Cond, Goal, State).
suspension(coroutines:call_when_disjoint(_, Next), Cond, Goal, State) :-
    suspension(Next, Cond, Goal, State).
suspension(coroutines:when_decidable_helper(_, Next), Cond, Goal, State) :-
    suspension(Next, Cond, Goal, State).

attr_unify_hook(Goal, Value) :-
    (attvar(Value) 
    ->
	    coroutines:put_when_attributes([Value], Goal),
	    walk_goals(Goal)
    ;
	    call(Goal)
    ).

walk_goals(Goal) :-
	Goal \= (_, _),
	check_decidable(Goal).

walk_goals(Goals) :-
	Goals = (Goal, Rest),
	check_decidable(Goal),
	walk_goals(Rest).

check_decidable(Goal) :-
    Goal \= coroutines:call_when_disjoint(_, _).

check_decidable(Goal) :-
    Goal = coroutines:call_when_disjoint(_, _),
	call(Goal).
