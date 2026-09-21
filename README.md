# Pyrolog

A Prolog interpreter in RPython.

Requires PyPy 2.7 (`pypy`), pytest 4.6.11, pexpect, GCC 12, and a PyPy source
checkout providing RPython (tested at `69e12f2c5c2cfe69529d5d7fcdcec048e1bd3ae4`).
Run from this repository's root:

```sh
export PYTHONPATH="$HOME/projects/gitpypy"

# Unit tests
pypy -m pytest -q prolog/interpreter/test prolog/builtin/test prolog/prolog_modules/test

# Translate with the JIT; produces ./pyrolog-c
CC=gcc-12 pypy "$PYTHONPATH/rpython/bin/rpython" --opt=jit targetprologstandalone.py

# Translated tracing, JIT, and terminal regression tests
PYROLOG_EXECUTABLE="$PWD/pyrolog-c" pypy -m pytest -q prolog/jittest/test_tracing.py
```
