"""Standalone infix-operator experiment. Run: pytest customopparser.py

Terminals are single ASCII digits; operators are single characters.
Trees are integers or (operator, left, right) tuples. No evaluation occurs.
"""


class ParseError(Exception):
    pass


class Operator(object):
    def __init__(self, precedence, form):
        assert 1 <= precedence <= 1200
        self.precedence = precedence
        self.form = form
        self.left_limit = self.right_limit = -1
        if form in ('yfx', 'xfy', 'xfx'):
            self.left_limit = precedence if form[0] == 'y' else precedence - 1
            self.right_limit = precedence if form[2] == 'y' else precedence - 1
            self.kind = 'infix'
        elif form in ('fx', 'fy'):
            self.right_limit = precedence if form[1] == 'y' else precedence - 1
            self.kind = 'prefix'
        elif form in ('xf', 'yf'):
            self.left_limit = precedence if form[0] == 'y' else precedence - 1
            self.kind = 'postfix'
        elif form == 'open_paren':
            # Barrier: every legal operator fits to its right.
            self.right_limit = 1200
            self.kind = 'open_paren'
        else:
            assert False, 'wrong form'

    def __repr__(self):
        return 'Operator(%d, %r)' % (self.precedence, self.form)


OPEN_PAREN = Operator(1200, 'open_paren')


DEFAULT_OPERATORS = {
    ('+', 'infix'): Operator(500, 'yfx'),
    ('-', 'infix'): Operator(500, 'yfx'),
    ('*', 'infix'): Operator(400, 'yfx'),
    ('^', 'infix'): Operator(200, 'xfy'),
    ('=', 'infix'): Operator(700, 'xfx'),
}


def tokenize(source):
    return [char for char in source if not char.isspace()]


class Parser(object):
    def __init__(self, tokens, operators):
        self.tokens = tokens
        self.operators = operators
        self.operands = []       # (tree, precedence)
        self.pending = []        # (operator character, definition)

    def __repr__(self):
        return 'Parser(tokens=%r, operands=%r, pending=%r, operators=%r)' % (
            self.tokens, self.operands, self.pending, self.operators)

    def parse(self):
        expect_operand = True
        for token in self.tokens:
            if expect_operand:
                if token == '(':
                    self.pending.append(('(', OPEN_PAREN))
                    continue
                prefix = self.operators.get((token, 'prefix'))
                if prefix:
                    self.pending.append((token, prefix))
                    continue
                if len(token) != 1 or token not in '0123456789':
                    raise ParseError('expected a digit, got %r' % token)
                self.operands.append((int(token), 0))
                expect_operand = False
            else:
                if token == ')':
                    while self.pending and self.pending[-1][1].kind != 'open_paren':
                        self._reduce()
                    if not self.pending:
                        raise ParseError("unmatched parenthesis")
                    self.pending.pop()
                    term, _ = self.operands.pop()
                    self.operands.append((term, 0))
                    continue
                incoming = self.operators.get((token, 'infix'))
                if incoming is not None:
                    self._reduce_before(incoming)
                    self.pending.append((token, incoming))
                    expect_operand = True
                    continue
                incoming = self.operators.get((token, 'postfix'))
                if incoming is None:
                    raise ParseError('expected an operator, got %r' % token)
                self._reduce_before(incoming)
                self.pending.append((token, incoming))
                expect_operand = False
                
        if expect_operand:
            # maybe we have ended with an infix that could be a postfix
            if self.pending:
                name, operator = self.pending[-1]
                postfix = self.operators.get((name, 'postfix'))
                if postfix:
                    self.pending.pop()
                    self.pending.append((name, postfix))
                    return self._finish()
            raise ParseError('expected a digit at end of input')
        return self._finish()

    def _finish(self):
        while self.pending:
            self._reduce()
        assert len(self.operands) == 1
        return self.operands[0][0]

    def _reduce_before(self, incoming):
        while self.pending:
            previous = self.pending[-1][1]
            # If the new expression can fit on the previous operator's
            # right, defer that operator. Otherwise finish it first.
            if incoming.precedence <= previous.right_limit:
                break
            self._reduce()

    def _reduce(self):
        name, operator = self.pending.pop()
        if operator.kind == 'open_paren':
            raise ParseError('parenthesis was never closed')
        if operator.kind == 'infix':
            right, right_precedence = self.operands.pop()
            left, left_precedence = self.operands.pop()
            if (left_precedence > operator.left_limit or
                    right_precedence > operator.right_limit):
                raise ParseError('operand precedence clash for %r' % name)
            tree = (name, left, right)
        elif operator.kind == 'prefix':
            right, right_precedence = self.operands.pop()
            if right_precedence > operator.right_limit:
                raise ParseError('operand precedence clash for %r' % name)
            tree = (name, right)
        elif operator.kind == 'postfix':
            left, left_precedence = self.operands.pop()
            if left_precedence > operator.left_limit:
                raise ParseError('operand precedence clash for %r' % name)
            tree = (name, left)
        else:
            assert 0, 'unknown kind'
        self.operands.append((tree, operator.precedence))


def parse(source, operators=None):
    if operators is None:
        operators = DEFAULT_OPERATORS
    return Parser(tokenize(source), operators).parse()


# Inline tests: these compare tree shapes, not arithmetic results.

def test_infix_reinterpreted_as_postfix_at_end():
    operators = {
        ('@', 'infix'): Operator(500, 'yfx'),
        ('@', 'postfix'): Operator(400, 'yf'),
    }
    assert parse('1@', operators) == ('@', 1)


def test_number():
    assert parse(' 7 ') == 7


def test_precedence():
    assert parse('1+2*3') == ('+', 1, ('*', 2, 3))
    assert parse('1*2+3') == ('+', ('*', 1, 2), 3)


def test_left_associative():
    assert parse('1-2-3') == ('-', ('-', 1, 2), 3)
    assert parse('1+2-3') == ('-', ('+', 1, 2), 3)


def test_right_associative():
    assert parse('1^2^3') == ('^', 1, ('^', 2, 3))


def test_non_associative():
    import pytest
    assert parse('1=2') == ('=', 1, 2)
    with pytest.raises(ParseError):
        parse('1=2=3')


def test_override_precedence():
    operators = dict(DEFAULT_OPERATORS)
    operators['+', 'infix'] = Operator(300, 'yfx')
    assert parse('1+2*3', operators) == ('*', ('+', 1, 2), 3)


def test_override_associativity():
    assert parse('1+2+3', {('+', 'infix'): Operator(500, 'xfy')}) == (
        '+', 1, ('+', 2, 3))


def test_custom_operator():
    assert parse('1@2', {('@', 'infix'): Operator(500, 'xfx')}) == ('@', 1, 2)


def test_mixed_equal_precedence():
    import pytest
    operators = {('+', 'infix'): Operator(500, 'xfy'), ('*', 'infix'): Operator(500, 'yfx')}
    assert parse('1+2*3', operators) == ('+', 1, ('*', 2, 3))
    with pytest.raises(ParseError):
        parse('1*2+3', operators)


def test_invalid_input():
    import pytest
    for source in ('', '12', '+1', '1+', '1++2', '1?2', 'a'):
        with pytest.raises(ParseError):
            parse(source)
    with pytest.raises(ParseError):
        parse('1+2', {})


# Prefix trees are (operator, operand).

def test_same_symbol_prefix_and_infix():
    operators = {
        ('+', 'prefix'): Operator(200, 'fy'),
        ('+', 'infix'): Operator(500, 'yfx'),
    }
    assert parse('+1++2', operators) == ('+', ('+', 1), ('+', 2))


def test_prefix_single_operand():
    for form in ('fx', 'fy'):
        assert parse('~1', {('~', 'prefix'): Operator(500, form)}) == ('~', 1)


def test_prefix_fy_chaining():
    assert parse('~~~1', {('~', 'prefix'): Operator(500, 'fy')}) == (
        '~', ('~', ('~', 1)))


def test_prefix_fx_rejects_equal_precedence():
    import pytest
    operators = {('~', 'prefix'): Operator(500, 'fx')}
    with pytest.raises(ParseError):
        parse('~~1', operators)


def test_prefix_different_precedences():
    import pytest
    operators = {('~', 'prefix'): Operator(500, 'fx'), ('!', 'prefix'): Operator(400, 'fx')}
    assert parse('~!1', operators) == ('~', ('!', 1))
    with pytest.raises(ParseError):
        parse('!~1', operators)


def test_prefix_and_infix_precedence():
    operators = dict(DEFAULT_OPERATORS)
    operators['~', 'prefix'] = Operator(450, 'fy')
    assert parse('~1*2+3', operators) == ('+', ('~', ('*', 1, 2)), 3)
    assert parse('1+~2*3', operators) == ('+', 1, ('~', ('*', 2, 3)))


def test_prefix_equal_precedence_infix():
    operators = {('~', 'prefix'): Operator(500, 'fx'), ('+', 'infix'): Operator(500, 'yfx')}
    assert parse('~1+2', operators) == ('+', ('~', 1), 2)
    operators['~', 'prefix'] = Operator(500, 'fy')
    assert parse('~1+2', operators) == ('~', ('+', 1, 2))


def test_prefix_operand_must_fit_infix():
    import pytest
    operators = {('+', 'infix'): Operator(500, 'yfx'), ('~', 'prefix'): Operator(500, 'fy')}
    # The right operand of yfx must have strictly smaller precedence.
    with pytest.raises(ParseError):
        parse('1+~2', operators)


def test_prefix_missing_operand():
    import pytest
    operators = {('~', 'prefix'): Operator(500, 'fy'), ('+', 'infix'): Operator(500, 'yfx')}
    for source in ('~', '~~', '~+1', '1+~'):
        with pytest.raises(ParseError):
            parse(source, operators)


def test_prefix_cannot_appear_after_operand():
    import pytest
    operators = {('~', 'prefix'): Operator(500, 'fy')}
    for source in ('1~', '1~2'):
        with pytest.raises(ParseError):
            parse(source, operators)


# Postfix trees also use (operator, operand).

def test_postfix_single_operand():
    for form in ('xf', 'yf'):
        assert parse('1!', {('!', 'postfix'): Operator(500, form)}) == ('!', 1)


def test_postfix_yf_chaining():
    assert parse('1!!!', {('!', 'postfix'): Operator(500, 'yf')}) == (
        '!', ('!', ('!', 1)))


def test_postfix_xf_rejects_equal_precedence():
    import pytest
    with pytest.raises(ParseError):
        parse('1!!', {('!', 'postfix'): Operator(500, 'xf')})


def test_postfix_different_precedences():
    import pytest
    operators = {
        ('!', 'postfix'): Operator(400, 'xf'),
        ('?', 'postfix'): Operator(500, 'xf'),
    }
    assert parse('1!?', operators) == ('?', ('!', 1))
    with pytest.raises(ParseError):
        parse('1?!', operators)


def test_postfix_and_infix_precedence():
    operators = dict(DEFAULT_OPERATORS)
    operators['!', 'postfix'] = Operator(300, 'yf')
    assert parse('1+2!', operators) == ('+', 1, ('!', 2))
    assert parse('1!+2', operators) == ('+', ('!', 1), 2)
    operators['!', 'postfix'] = Operator(600, 'yf')
    assert parse('1+2!', operators) == ('!', ('+', 1, 2))


def test_postfix_equal_precedence_infix():
    import pytest
    operators = {
        ('+', 'infix'): Operator(500, 'yfx'),
        ('!', 'postfix'): Operator(500, 'yf'),
    }
    assert parse('1+2!', operators) == ('!', ('+', 1, 2))
    assert parse('1!+2', operators) == ('+', ('!', 1), 2)
    operators['!', 'postfix'] = Operator(500, 'xf')
    # Neither grouping works: both operators require a tighter operand
    # on the side where the other operator's result would appear.
    with pytest.raises(ParseError):
        parse('1+2!', operators)


def test_postfix_and_prefix_precedence():
    operators = {
        ('~', 'prefix'): Operator(500, 'fy'),
        ('!', 'postfix'): Operator(400, 'yf'),
    }
    assert parse('~1!', operators) == ('~', ('!', 1))
    operators['!', 'postfix'] = Operator(600, 'yf')
    assert parse('~1!', operators) == ('!', ('~', 1))


def test_postfix_and_prefix_strict_clash():
    import pytest
    operators = {
        ('~', 'prefix'): Operator(500, 'fx'),
        ('!', 'postfix'): Operator(500, 'xf'),
    }
    with pytest.raises(ParseError):
        parse('~1!', operators)


def test_postfix_invalid_placement():
    import pytest
    operators = {('!', 'postfix'): Operator(500, 'yf')}
    for source in ('!', '!1', '1!2'):
        with pytest.raises(ParseError):
            parse(source, operators)


def test_parenthesized_number():
    assert parse('(1)') == 1
    assert parse('((1))') == 1


def test_parentheses_override_precedence():
    assert parse('(1+2)*3') == ('*', ('+', 1, 2), 3)
    assert parse('1*(2+3)') == ('*', 1, ('+', 2, 3))


def test_parentheses_override_associativity():
    assert parse('1-(2-3)') == ('-', 1, ('-', 2, 3))
    assert parse('(1^2)^3') == ('^', ('^', 1, 2), 3)


def test_parentheses_reset_precedence():
    assert parse('(1=2)=3') == ('=', ('=', 1, 2), 3)
    assert parse('1=(2=3)') == ('=', 1, ('=', 2, 3))


def test_parentheses_keep_operator_stacks_separate():
    assert parse('1+(2+3)*4') == ('+', 1, ('*', ('+', 2, 3), 4))
    assert parse('(1+2)*(3+4)') == ('*', ('+', 1, 2), ('+', 3, 4))
    assert parse('1*(2+(3*4))+5') == (
        '+', ('*', 1, ('+', 2, ('*', 3, 4))), 5)


def test_parentheses_with_prefix():
    operators = dict(DEFAULT_OPERATORS)
    operators['~', 'prefix'] = Operator(300, 'fx')
    assert parse('~(1+2)', operators) == ('~', ('+', 1, 2))
    assert parse('~(~1)', operators) == ('~', ('~', 1))
    assert parse('(~1)+2', operators) == ('+', ('~', 1), 2)


def test_parentheses_with_postfix():
    operators = dict(DEFAULT_OPERATORS)
    operators['!', 'postfix'] = Operator(300, 'xf')
    assert parse('(1+2)!', operators) == ('!', ('+', 1, 2))
    assert parse('(1!)!', operators) == ('!', ('!', 1))
    assert parse('1+(2!)', operators) == ('+', 1, ('!', 2))


def test_parentheses_do_not_relax_inner_precedence():
    import pytest
    with pytest.raises(ParseError):
        parse('(1=2=3)')


def test_invalid_parentheses():
    import pytest
    for source in ('()', '(1', '1)', '(1))', '((1)', '(1+)',
                   '1(2)', '(1)2', '(1)(2)', '1+()'):
        with pytest.raises(ParseError):
            parse(source)
