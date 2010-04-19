from prolog.interpreter.function import Rule, Function, Rulechain
from prolog.interpreter.term import Callable, Var
from prolog.interpreter.signature import Signature
from prolog.interpreter.test.tool import get_engine

class C(Callable):
    def __init__(self, name):
        self._name = name
    def __eq__(self, other):
        return self.name() == other.name()    
    def __str__(self):
        return 'C(%s)' % self.name()    
    def signature(self):
        return Signature(self.name(), 123)
    def name(self):
        return 'C'
    def argument_count(self):
        return 0
    def arguments(self):
        return []
    __repr__ = __str__

def test_copy():
            
    l1 = Rulechain(Rule(C('a'), C('a1')), Rulechain(Rule(C('b'), C('b1')), Rulechain(Rule(C('c'), C('c1')))))
    l1c, _ = l1.copy()

    t1 = l1
    t2 = l1c
    while t1 is not None:
        assert t1 is not t2
        assert t1 == t2
        t1 = t1.next
        t2 = t2.next

    l0 = Rulechain(Rule(C(-1), C('a')), Rulechain(Rule(C(-2), C('b')), Rulechain(Rule(C(-3), C('c')), l1)))
    l0c, end = l0.copy(l1)
    t1 = l0
    t2 = l0c
    while t1 is not l1:
        assert t1 == t2
        assert t1 is not t2
        t1 = t1.next
        prev = t2
        t2 = t2.next
    assert t2 is l1
    assert prev is end
    
def test_function():
    def get_rules(chain):
        r = []
        while chain:
            r.append((chain.rule.head, chain.rule.body))
            chain = chain.next
        return r
    f = Function()
    r1 = Rule(C(1), C(2))
    r2 = Rule(C(2), C(3))
    r3 = Rule(C(0), C(0))
    r4 = Rule(C(15), C(-1))
    f.add_rule(r1, True)
    assert get_rules(f.rulechain) == [(C(1), C(2))]
    f.add_rule(r2, True)
    assert get_rules(f.rulechain) == [(C(1), C(2)), (C(2), C(3))]
    f.add_rule(r3, False)
    assert get_rules(f.rulechain) == [(C(0), C(0)), (C(1), C(2)), (C(2), C(3))]

    # test logical update view
    rulechain = f.rulechain
    f.add_rule(r4, True)
    assert get_rules(rulechain) == [(C(0), C(0)), (C(1), C(2)), (C(2), C(3))]
    assert get_rules(f.rulechain) == [(C(0), C(0)), (C(1), C(2)), (C(2), C(3)), (C(15), C(-1))]

def test__split_by_signature():
    def shorter(result):
        if isinstance(result[0], tuple):
            return [(a.name, [r.headargs[-1].num for r in b])
                        for a, b in result]
        return [r.headargs[-1].num for r in result]
    e = get_engine("""
    f(a, A, -1).
    f(a, a, 0).
    f(a, b, 1).
    f(b, X, 2).
    f(c, a, 3).
    f(1, 2, 4).

    g(a, 0).
    g(b, 1).
    """)

    rulechain = e._lookup(Signature.getsignature("f", 3)).rulechain
    split, more = rulechain._split_by_signature(0)
    assert shorter(more) == [4]
    assert shorter(split) == [("a", [-1, 0, 1, 4]), ("b", [2, 4]), ("c", [3, 4])]
    split, more = rulechain._split_by_signature(1)
    assert shorter(more) == [-1, 2, 4]
    assert shorter(split) == [("a", [-1, 0, 2, 3, 4]), ("b", [-1, 1, 2, 4])]
    rulechain = e._lookup(Signature.getsignature("g", 2)).rulechain
    split, more = rulechain._split_by_signature(0)
    assert shorter(split) == [("a", [0]), ("b", [1])]
    assert not more

def test_get_index_dict():
    def shorter(d):
        return dict([(k.name, [r.headargs[-1].num for r in v.all_rules()])
                        for k, v in d.iteritems()])

    e = get_engine("""
    f(a, A, -1).
    f(a, a, 0).
    f(a, b, 1).
    f(b, X, 2).
    f(c, a, 3).
    f(1, 2, 4).
    """)

    rulechain = e._lookup(Signature.getsignature("f", 3)).rulechain
    d = rulechain.get_index_dict(0)
    assert shorter(d) == {
        "a": [-1, 0, 1, 4],
        "b": [2, 4],
        "c": [3, 4],
    }
    for rc in d.values():
        assert rc.index == 0

    d = rulechain.get_index_dict(1)
    assert shorter(d) == {
        "a": [-1, 0, 2, 3, 4],
        "b": [-1, 1, 2, 4],
    }
    for rc in d.values():
        assert rc.index == 1

def test_find_rulechain():
    e = get_engine("""
    f(a, A, -1).
    f(a, a, 0).
    f(a, b, 1).
    f(b, X, 2).
    f(c, a, 3).
    f(1, 2, 4).

    g(a, 0).
    g(b, 1).
    """)

    query = Callable.build("f", [Callable.build("a"), Callable.build("b"), Var()])
    rulechain = e._lookup(query.signature()).rulechain
    rc = rulechain.find_rulechain(query)
    assert rc.rule.headargs[-1].num == -1
    rc = rc.next
    assert rc.rule.headargs[-1].num == 1
    rc = rc.next
    assert rc.rule.headargs[-1].num == 4
    assert rc.next is None

    query = Callable.build("f", [Callable.build("b"), Callable.build("c"), Var()])
    rc = rulechain.find_rulechain(query)
    assert rc.rule.headargs[-1].num == 2
    rc = rc.next
    assert rc.rule.headargs[-1].num == 4
    assert rc.next is None

    query = Callable.build("g", [Callable.build("c"), Var()])
    rulechain = e._lookup(query.signature()).rulechain
    rulechain._depth = 10 # cheat a bit
    rc = rulechain.find_rulechain(query)
    assert rc is None
    

