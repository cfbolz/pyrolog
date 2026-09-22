# rpyrepl

A small RPython terminal editor, independent of Pyrolog. Its reader, command,
and console interfaces follow pyrepl. Editing algorithms are adapted from
pyrepl; see LICENSE. The initial implementation uses a single row with
horizontal scrolling, UTF-8 input, and terminfo capabilities on Unix.

Supported keys: printable text, Backspace, Delete, Left/Right, Home/End,
Ctrl-A/B/E/F, Up/Down and Ctrl-P/N (history), Enter, Ctrl-D (EOF on an empty
buffer), and Ctrl-C (cancel input).
Alt-B/F and Ctrl-Left/Right move by words. Ctrl-arrow sequences from xterm
compatible terminals and rxvt are supported. Ctrl-W and Alt-Backspace delete
the preceding word; Alt-D deletes the following word. These use the same word
boundaries: Unicode letters, numbers, combining marks, and underscore belong
to words; punctuation separates them. Ctrl-U/K delete to the beginning/end
of the buffer. Ctrl-Y reinserts deleted text; consecutive deletion commands
combine their text in order. There is one saved deletion, retained across
queries, rather than a full kill ring.
Completion, colourization, multiline editing, and bracketed paste
are not implemented yet. Resize is reflected on the next input event.

`make_reader()` returns a Reader, or None when stdin/stdout are not terminals
or the terminal lacks the required capabilities. `Reader.readline(prompt)`
takes and returns UTF-8 byte strings; EOF and cancellation raise this package's
`EndOfInput` and `CancelledInput`. Terminal modes are restored before it returns
or raises. Applications own the plain-input fallback and history policy.

Pass a `rpyrepl.history.History()` as `make_reader(history=history)` to
enable in-memory history, and call `history.append(text)` to record UTF-8
input. Navigation restores the unfinished draft and cursor when moving beyond
the newest entry. Edits to recalled entries are discarded when navigating away;
stored entries are unchanged. History is unlimited. `history.load(path)` reads
existing entries at startup; `history.save(path)` appends only unsaved entries
to that same file. The format follows pyrepl: LF separates entries and CRLF
represents a newline within an entry. Malformed UTF-8 entries are skipped.

Pyrolog records nonblank accepted queries and omits consecutive duplicates.
Interactive sessions load `~/.pyrolog_history` and append each query before
execution. Set `PYROLOG_HISTORY` to choose another filename, or to the empty
string to disable persistence. New files have owner-only permissions. File
errors produce a warning while in-memory editing and history remain usable.
There is no exit-time rewrite or truncation, so concurrent sessions preserve
each other's appended entries. Other sessions' entries become available on
the next startup. Piped input does not access the history file.

Text is stored as UTF-8 using `rpython.rlib.rutf8`, without RPython's Unicode
type. Cursor and scroll offsets are byte positions at code-point boundaries;
screen coordinates are terminal columns. Prompts, inserted text, and history
entries are validated, rejecting malformed UTF-8 and surrogates with
`rutf8.CheckError`. Invalid terminal input is ignored. Movement and deletion
operate on code points, not grapheme clusters; display widths still use the
Unicode 15.0 database and do not fully handle emoji grapheme sequences.

Run from the repository root, with PYTHONPATH pointing to an RPython checkout:

```sh
pypy -m pytest -q rpyrepl/test --ignore=rpyrepl/test/test_translated.py
CC=gcc-12 PYTHONPATH="$PWD:$PYTHONPATH" pypy "$PYTHONPATH/rpython/bin/rpython" --batch --output=rpyrepl-c rpyrepl/test/targetrpyrepl.py
RPYREPL_EXECUTABLE="$PWD/rpyrepl-c" pypy -m pytest -q rpyrepl/test/test_translated.py
```

The standalone target checks that the original terminal attributes are restored
on acceptance, cancellation, and EOF. It has no imports from Pyrolog.
