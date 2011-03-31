from __future__ import with_statement
import py
import sys, os, re
from pypy.tool.udir import udir

app_main = py.path.local(__file__).dirpath().dirpath().join("translatedmain.py")
app_main.check()
path = str(app_main.dirpath().dirpath().dirpath()) + ":" + os.environ["PYTHONPATH"]
app_main = str(app_main)


class TestInteraction:
    def _spawn(self, *args, **kwds):
        try:
            import pexpect
        except ImportError, e:
            py.test.skip(str(e))
        else:
            version = map(int, pexpect.__version__.split('.'))
            if version < [2, 1]:
                py.test.skip(
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
        child.expect("Y = _G0")
        child.expect("X = _G0")
        child.expect(">?- ")

        child.sendline("X = f(a, Y), Y = 8.")
        child.expect("yes")
        child.expect("Y = 8")
        child.expect(re.escape("X = f(a, 8)"))
        child.expect(">?- ")

        child.sendline("X = 1, X = 2.")
        child.expect("no")
        child.expect(">?- ")

        child.sendline("X = [a, b, Y], Y = [1, 2], Z = Y.")
        child.expect("yes")
        child.expect(re.escape("Y = [1, 2]"))
        child.expect(re.escape("X = [a, b, [1, 2]]"))
        child.expect(re.escape("Z = [1, 2]"))
        child.expect(">?- ")

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
        child.expect("no")
        child.expect(">?- ")

    def test_attvar(self):
        child = self.spawn([])
        child.expect("welcome!")
        child.expect(">?- ")
        child.sendline("put_attr(X, m, 1).")
        child.expect("yes")
        child.expect("X = _G0")
        child.expect(re.escape("put_attr(_G0, m, 1)"))
        child.expect(">?- ")

        child.sendline("put_attr(X, a, b), put_attr(X, b, c), put_attr(Y, x, 1).")
        child.expect("yes")
        child.expect("Y = _G0")
        child.expect("X = _G1")
        child.expect(re.escape("put_attr(_G0, x, 1)"))
        child.expect(re.escape("put_attr(_G1, a, b)"))
        child.expect(re.escape("put_attr(_G1, b, c)"))
        child.expect(">?- ")

        child.sendline("assert(m:attr_unify_hook(_, _)).")
        child.expect("yes")
        child.expect(">?- ")

        child.sendline("put_attr(X, m, 1), X = a.")
        child.expect("yes")
        child.expect("X = a")
        child.expect(">?- ")

        child.sendline("put_attr(X, m, 1), ((X = a, write(output), nl, fail); true).")
        child.expect("output")
        child.expect("yes")
        child.expect("X = _G0")
        child.expect(re.escape("put_attr(_G0, m, 1)"))
        child.expect(">?- ")

        child.sendline("put_attr(X, m, 1), del_attr(X, m).")
        child.expect("yes")
        child.expect(">?- ")
