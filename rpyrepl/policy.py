"""Applications decide whether Enter needs another logical line."""


class InputPolicy(object):
    def more_lines(self, text):
        return False


class BalancedParens(InputPolicy):
    """Small example policy for the standalone editor target."""
    def more_lines(self, text):
        depth = 0
        for char in text:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
                if depth < 0:
                    return False
        return depth > 0
