from __future__ import with_statement
import pytest
import py
import sys, os, re
from rpython.tool.udir import udir

app_main = py.path.local(__file__).dirpath().dirpath().join("translatedmain.py")
app_main.check()
path = str(app_main.dirpath().dirpath().dirpath()) + ":" + os.environ["PYTHONPATH"]
path += ":" + str(py.path.local(sys.modules['rpython'].__file__).dirpath().dirpath())
app_main = str(app_main)


class TestInteraction:
    @pytest.mark.parametrize('query, prompt', [
        ('', '>?- '),
        ('(X = a; X = b).', 'X = a'),
        ('trace.\ntrue.', 'Call: (1) true'),
    ])
    def test_ctrl_d(self, query, prompt):
        child = self.spawn([])
        import pexpect
        if query:
            child.expect(re.escape('>?- '))
            child.sendline(query)
        child.expect(re.escape(prompt))
        child.sendcontrol('d')
        child.expect(pexpect.EOF)
        assert 'Traceback' not in child.before
        child.close()
        assert child.exitstatus == 0

    def _spawn(self, *args, **kwds):
        try:
            import pexpect
        except ImportError, e:
            pytest.skip(str(e))
        else:
            version = map(int, pexpect.__version__.split('.'))
            if version < [2, 1]:
                pytest.skip(
                    "pexpect version too old, requires 2.1 or newer: %r" % (
                        pexpect.__version__,))

        kwds.setdefault('timeout', 10)
        print 'SPAWN:', args, kwds
        child = pexpect.spawn(*args, **kwds)
        child.logfile = sys.stdout
        return child

    def spawn(self, argv):
        env = {"PYTHONPATH": str(path), "PATH": os.environ["PATH"]}
        return self._spawn(sys.executable, [app_main] + argv, env=env)

    def expect_bindings(self, child, bindings):
        child.expect(re.escape('>?- '))
        # Variable dictionary iteration order is not part of the console API.
        actual = [line.strip() for line in child.before.splitlines()
                  if re.match(r'^[A-Z][A-Za-z0-9_]* = ', line.strip())]
        assert sorted(actual) == sorted(bindings)

    def test_simple_unifications(self):
        child = self.spawn([])
        child.expect("welcome!")
        child.expect(">?- ")
        child.sendline("X = 1.")
        child.expect("yes")
        child.expect("X = 1")
        child.expect(">?- ")

        child.sendline("X = Y.")
        child.expect("yes")
        self.expect_bindings(child, ["X = _G0", "Y = _G0"])

        child.sendline("X = f(a, Y), Y = 8.")
        child.expect("yes")
        self.expect_bindings(child, ["X = f(a, 8)", "Y = 8"])

        child.sendline("X = 1, X = 2.")
        child.expect("Nein")
        child.expect(">?- ")

        child.sendline("X = [a, b, Y], Y = [1, 2], Z = Y.")
        child.expect("yes")
        self.expect_bindings(child, ["X = [a, b, [1, 2]]",
                                     "Y = [1, 2]", "Z = [1, 2]"])

    def test_more_than_one_solution(self):
        child = self.spawn([])
        child.expect("welcome!")
        child.expect(">?- ")
        child.sendline("X = 1; X = 2; X = 3.")
        child.expect("yes")
        child.expect("X = 1")
        child.sendline(";")
        child.expect("yes")
        child.expect("X = 2")
        child.sendline(";")
        child.expect("yes")
        child.expect("X = 3")
        child.expect(">?- ")

        child.sendline("atom_concat(A, B, abc).")
        child.expect("yes")
        child.expect("A = ''")
        child.expect("B = abc")
        child.sendline(";")
        child.expect("A = a")
        child.expect("B = bc")
        child.sendline(";")
        child.expect("A = ab")
        child.expect("B = c")
        child.sendline(";")
        child.expect("A = abc")
        child.expect("B = ''")
        child.sendline(";")
        child.expect(">?- ")

    def test_parse_error(self):
        child = self.spawn([])
        child.expect("welcome!")
        child.expect(">?- ")
        child.sendline("X = $.")
        child.expect("  File <stdin>, line 1")
        child.expect(re.escape("X = $."))
        child.expect(re.escape("    ^"))
        child.expect("LexerError")

        child = self.spawn([])
        child.expect("welcome!")
        child.expect(">?- ")
        child.sendline("X = a b c.")
        child.expect("  File <stdin>, line 1")
        child.expect(re.escape("X = a b c."))
        child.expect(re.escape("      ^"))
        child.expect(re.escape("ParseError: expected ."))

    def test_traceback(self):
        child = self.spawn([])
        child.expect("welcome!")
        child.expect(">?- ")
        child.sendline("assert((f(X) :- X is X)).")
        child.expect("yes")
        child.sendline("f(X).")
        child.expect(re.escape("ERROR:"))
        child.expect(re.escape("Traceback (most recent call last):"))
        child.expect(re.escape('  File "<unknown>" in user:f/1'))
        child.expect(re.escape("arguments not sufficiently instantiated"))
