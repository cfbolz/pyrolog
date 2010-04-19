from prolog.interpreter.term import Callable
from prolog.interpreter.memo import EnumerationMemo
from prolog.interpreter.signature import Signature
from pypy.rlib import jit, objectmodel, unroll
# XXX needs tests

cutsig = Signature.getsignature("!", 0)

class Rule(object):
    _immutable_ = True
    _immutable_fields_ = ["headargs[*]"]
    _attrs_ = ['head', 'headargs', 'contains_cut', 'body', 'size_env', 'signature']
    unrolling_attrs = unroll.unrolling_iterable(_attrs_)
    
    def __init__(self, head, body):
        from prolog.interpreter import helper
        assert isinstance(head, Callable)
        memo = EnumerationMemo()
        self.head = h = head.enumerate_vars(memo)
        if h.argument_count() > 0:
            self.headargs = h.arguments()
        else:
            self.headargs = None
        if body is not None:
            body = helper.ensure_callable(body)
            self.body = body.enumerate_vars(memo)
        else:
            self.body = None
        self.size_env = memo.size()
        self.signature = head.signature()        
        self._does_contain_cut()


    def _does_contain_cut(self):
        if self.body is None:
            self.contains_cut = False
            return
        stack = [self.body]
        while stack:
            current = stack.pop()
            if isinstance(current, Callable):
                if current.signature().eq(cutsig):
                    self.contains_cut = True
                    return
                else:
                    stack.extend(current.arguments())
        self.contains_cut = False

    @jit.unroll_safe
    def clone_and_unify_head(self, heap, head):
        env = [None] * self.size_env
        if self.headargs is not None:
            assert isinstance(head, Callable)
            for i in range(len(self.headargs)):
                arg2 = self.headargs[i]
                arg1 = head.argument_at(i)
                arg2.unify_and_standardize_apart(arg1, heap, env)
        body = self.body
        if body is None:
            return None
        return body.copy_standardize_apart(heap, env)


    @jit.unroll_safe
    def can_match(self, query):
        if self.headargs is not None:
            assert isinstance(query, Callable)
            for i in range(len(self.headargs)):
                arg2 = self.headargs[i]
                arg1 = query.argument_at(i)
                if not arg2.quick_unify_check(arg1):
                    return False
        return True

    def __repr__(self):
        if self.body is None:
            return "%s." % (self.head, )
        return "%s :- %s." % (self.head, self.body)

def _make_chain(l, argindex=-1):
    chain = None
    for i in range(len(l)-1, -1, -1):
        rule = l[i]
        chain = Rulechain(rule, chain, argindex)
    return chain

class Rulechain(object):
    _immutable_ = True
    def __init__(self, rule, next=None, index=-1):
        self.rule = rule
        self.next = next
        self.index = index
        self.index_dicts = None
        self.index_restchain = None
        self._depth = -1

    @jit.purefunction
    def depth(self):
        if self._depth == -1:
            if self.next is None:
                self._depth = 0
                return 0
            self._depth = self.next.depth() + 1
        return self._depth
        
    def instance_copy(self):
        return Rulechain(self.rule, self.next, self.index)

    def copy(self, stopat=None):
        first = self.instance_copy()
        curr = self.next
        copy = first
        while curr is not stopat:
            # if this is None, the stopat arg was invalid
            assert curr is not None
            new = curr.instance_copy()
            copy.next = new
            copy = new
            curr = curr.next
        return first, copy
        
    def all_rules(self):
        res = []
        while self:
            res.append(self.rule)
            self = self.next
        return res

    def _split_by_signature(self, argindex):
        result = []
        rules = self.all_rules()
        while True:
            signature = None
            slice = []
            rest = []
            for i in range(len(rules)):
                rule = rules[i]
                arg = rule.headargs[argindex]
                if isinstance(arg, Callable):
                    if signature is None:
                        signature = arg.signature()
                        slice.append(rule)
                    else:
                        if signature.eq(arg.signature()):
                            slice.append(rule)
                        else:
                            rest.append(rule)
                else:
                    slice.append(rule)
                    rest.append(rule)
                    
            if signature:
                result.append((signature, slice))
                rules = rest
            else:
                return result, rest

    def _compute_index_dict(self, argindex):
        index_dict = self.index_dicts[argindex] = {}
        res, rest = self._split_by_signature(argindex)
        self.index_restchain[argindex] = _make_chain(rest, argindex)
        for sig, l in res:
            index_dict[sig] = _make_chain(l, argindex)
        return index_dict

    def get_index_dict(self, argindex):
        if self.index_dicts is None:
            self.index_dicts = [None] * len(self.rule.headargs)
            self.index_restchain = [None] * len(self.rule.headargs)
            index_dict = None
        else:
            index_dict = self.index_dicts[argindex]
        if index_dict is None:
            index_dict = self._compute_index_dict(argindex)
        return index_dict

    @jit.purefunction
    def get_index_chain(self, argindex, signature):
        signature = signature.ensure_cached()
        index_dict = self.get_index_dict(argindex)
        res = index_dict.get(signature, None)
        if res is None:
            return self.index_restchain[argindex]
        return res

    @jit.unroll_safe
    def find_rulechain(self, query):
        if self.depth() < 5: # magic number, adjust
            return self
        # perform indexing
        argindex = self.index
        while self:
            argindex = query.find_indexable_arg(argindex)
            if argindex == -1:
                return self
            self = self.get_index_chain(argindex,
                                        query.arg_signature(argindex))

    @jit.unroll_safe
    def find_applicable_rule(self, query):
        # This method should do some quick filtering on the rules to filter out
        # those that cannot match query.
        while self is not None:
            if self.rule.can_match(query):
                return self
            self = self.next
        return None

    def find_next_applicable_rule(self, query):
        if self.next is None:
            return None
        return self.next.find_applicable_rule(query)
    
    def __repr__(self):
        return "Rulechain(%r, %r)" % (self.rule, self.next)
    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.__dict__ == other.__dict__
    def __ne__(self, other):
        return not self == other


class Function(object):
    def __init__(self, firstrule=None):
        self.rulechain = self.last = None

    def add_rule(self, rule, atend):
        rulechain = Rulechain(rule)
        if self.rulechain is None:
            self.rulechain = self.last = rulechain
        elif atend:
            self.rulechain, last = self.rulechain.copy()
            self.last = rulechain
            last.next = self.last
        else:
            rulechain.next = self.rulechain
            self.rulechain = rulechain

    def remove(self, rulechain):
        self.rulechain, last = self.rulechain.copy(rulechain)
        last.next = rulechain.next
