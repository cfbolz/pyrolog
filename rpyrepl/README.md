# rpyrepl

A small RPython terminal editor, independent of Pyrolog. Its reader, command,
and console interfaces follow pyrepl. Editing algorithms are adapted from
pyrepl; see LICENSE. The initial implementation uses a single row with
horizontal scrolling, UTF-8 input, and terminfo capabilities on Unix.

Supported keys: printable text, Backspace, Delete, Left/Right, Home/End,
Ctrl-A/B/E/F, Up/Down and Ctrl-P/N (history), Enter, Ctrl-D (EOF on an empty
buffer), and Ctrl-C (cancel input).
Persistent history, completion, colourization, multiline editing, and bracketed paste
are not implemented yet. Resize is reflected on the next input event.

`make_reader()` returns a Reader, or None when stdin/stdout are not terminals
or the terminal lacks the required capabilities. `Reader.readline(prompt)`
takes and returns Unicode; EOF and cancellation raise this package's
`EndOfInput` and `CancelledInput`. Terminal modes are restored before it returns
or raises. Applications own the plain-input fallback and history policy.

Pass a `rpyrepl.history.History(limit)` as `make_reader(history=history)` to
enable in-memory history, and call `history.append(text)` to record Unicode
input. Navigation restores the unfinished draft and cursor when moving beyond
the newest entry. Edits to recalled entries are discarded when navigating away;
stored entries are unchanged. Pyrolog records nonblank accepted queries, omits
consecutive duplicates, and retains at most 1,000 entries per session.

Run from the repository root, with PYTHONPATH pointing to an RPython checkout:

```sh
pypy -m pytest -q rpyrepl/test --ignore=rpyrepl/test/test_translated.py
CC=gcc-12 PYTHONPATH="$PWD:$PYTHONPATH" pypy "$PYTHONPATH/rpython/bin/rpython" --batch --output=rpyrepl-c rpyrepl/test/targetrpyrepl.py
RPYREPL_EXECUTABLE="$PWD/rpyrepl-c" pypy -m pytest -q rpyrepl/test/test_translated.py
```

The standalone target checks that the original terminal attributes are restored
on acceptance, cancellation, and EOF. It has no imports from Pyrolog.
