# Pyrolog

A Prolog interpreter in RPython.

The interactive REPL supports editing, persistent history, highlighting, and
predicate/module completion. See [rpyrepl](rpyrepl/README.md) for keys and settings.

Text is stored internally as UTF-8 byte strings. Atoms may contain any Unicode
scalar value, including NUL; lengths, character codes, and `sub_atom/5` offsets
count code points. Text is not normalized: `é` and `e` followed by a combining
accent remain distinct atoms. Quoted atoms support `\uXXXX`, `\UXXXXXXXX`, and
terminated hexadecimal/octal escapes. Double-quoted text remains a list of
character codes, not a separate string type.

Source identifiers use Unicode 15.0 XID character classes; an initial uppercase
letter or underscore introduces a variable. Lexer source offsets remain byte
offsets, while diagnostic columns count code points. Printing, highlighting,
and predicate completion use the same lexical rules.

Text streams use UTF-8 (`encoding(utf8)`); malformed UTF-8 raises
`representation_error(character)`. `get_char/2`, `get_code/2`, their peek
variants, `put_char/2`, and `put_code/2` operate on complete characters. Open
streams with `type(binary)` for `get_byte/2`, `peek_byte/2`, and `put_byte/2`;
byte operations and text operations reject streams of the wrong type. Other
text encodings are not yet supported. `seek/4` positions are byte offsets.
NUL is allowed in atoms but rejected in filesystem paths.

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
