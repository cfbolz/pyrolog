# Pyrolog

A Prolog interpreter in RPython.

The interactive REPL supports editing, persistent history, highlighting, and
predicate/module completion. See [rpyrepl](rpyrepl/README.md) for keys and settings.

Requires PyPy 2.7 (`pypy`), pytest 4.6.11, pexpect, GCC 12, ncurses development headers, and a PyPy source
checkout providing RPython (tested at `69e12f2c5c2cfe69529d5d7fcdcec048e1bd3ae4`).
Run from this repository's root:

```sh
export PYTHONPATH="$HOME/projects/gitpypy"
pypy -m pip install -r ci/requirements.txt

# Unit tests
pypy -m pytest -q prolog/interpreter/test prolog/builtin/test prolog/prolog_modules/test rpyrepl/test --ignore=rpyrepl/test/test_translated.py

# Translate with the JIT; produces ./pyrolog-c
CC=gcc-12 pypy "$PYTHONPATH/rpython/bin/rpython" --opt=jit targetprologstandalone.py

# Translated tracing, JIT, and terminal regression tests
PYROLOG_EXECUTABLE="$PWD/pyrolog-c" pypy -m pytest -q prolog/jittest
```
