"""Suggestions for uncaught undefined calls; never used during execution.

The bounded distance algorithm is adapted from PyPy's Python 3.12
lib-python/3/traceback.py (originally CPython). License:
https://docs.python.org/3.12/license.html
Here inputs are lists of Unicode code points, suitable for RPython.
"""
from rpython.rlib import rutf8
from rpython.rlib.listsort import TimSort, make_timsort_class
from prolog.interpreter.utf8 import unicodedb
from prolog.interpreter.predicates import visible_predicates

MOVE_COST = 2
CASE_COST = 1
MAX_STRING_SIZE = 40


def arity_lt(a, b):
    return a[0] < b[0] or (a[0] == b[0] and a[1] < b[1])


AritySort = make_timsort_class(lt=arity_lt)


def substitution_cost(a, b):
    if a == b:
        return 0
    if unicodedb.tolower_full(a) == unicodedb.tolower_full(b):
        return CASE_COST
    return MOVE_COST


def levenshtein_distance(a, b, max_cost):
    """Exact distance within budget, otherwise a value greater than budget."""
    start = 0
    while start < len(a) and start < len(b) and a[start] == b[start]:
        start += 1
    aend, bend = len(a), len(b)
    while aend > start and bend > start and a[aend - 1] == b[bend - 1]:
        aend -= 1
        bend -= 1
    assert aend >= 0 and bend >= 0
    a, b = a[start:aend], b[start:bend]
    if not a or not b:
        return (len(a) + len(b)) * MOVE_COST
    if len(a) > MAX_STRING_SIZE or len(b) > MAX_STRING_SIZE:
        return max_cost + 1
    if len(b) < len(a):
        a, b = b, a
    if (len(b) - len(a)) * MOVE_COST > max_cost:
        return max_cost + 1
    row = [(i + 1) * MOVE_COST for i in range(len(a))]
    result = 0
    for bindex in range(len(b)):
        diagonal = result = bindex * MOVE_COST
        minimum = max_cost + 1
        for index in range(len(a)):
            substitute = diagonal + substitution_cost(b[bindex], a[index])
            diagonal = row[index]
            result = min(substitute, min(result, diagonal) + MOVE_COST)
            row[index] = result
            minimum = min(minimum, result)
        if minimum > max_cost:
            return max_cost + 1
    return result


def predicate_suggestions(engine, module, missing):
    """Return (other arities, equally best spelling matches), capped at three."""
    candidates = visible_predicates(engine, module, include_empty=True)
    arities = []
    names = []
    by_name = {}
    for candidate in candidates:
        if candidate.name == missing.name:
            if candidate.numargs != missing.numargs:
                arities.append((abs(candidate.numargs - missing.numargs),
                                candidate.numargs))
        elif candidate.numargs == missing.numargs:
            names.append(candidate.name)
            by_name[candidate.name] = candidate
    AritySort(arities).sort()
    other_arities = []
    from prolog.interpreter.signature import Signature
    for distance, arity in arities[:3]:
        other_arities.append(Signature.getsignature(missing.name, arity))
    # Keep expensive matching bounded, without hiding exact-name arity hints.
    if missing.name_length > MAX_STRING_SIZE or len(names) >= 750:
        return other_arities, []
    TimSort(names).sort()
    wrong = [code for code in rutf8.Utf8StringIterator(missing.name)]
    best = len(wrong) - 1
    matches = []
    for name in names:
        candidate = by_name[name]
        budget = min(best, (missing.name_length + candidate.name_length + 3)
                     * MOVE_COST // 6)
        if abs(candidate.name_length - missing.name_length) * MOVE_COST > budget:
            continue
        right = [code for code in rutf8.Utf8StringIterator(name)]
        distance = levenshtein_distance(wrong, right, budget)
        if distance > budget:
            continue
        if distance < best:
            matches = []
            best = distance
        if len(matches) < 3:
            matches.append(candidate)
    return other_arities, matches
