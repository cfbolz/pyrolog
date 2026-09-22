# rpyrepl

A small RPython terminal editor, independent of Pyrolog. Its reader, command,
and console interfaces follow pyrepl. Editing algorithms are adapted from
pyrepl; see LICENSE. The implementation uses UTF-8 input, multiline editing,
and terminfo capabilities on Unix. Logical lines wrap into screen rows with
a visible backslash marking each wrap; the marker is not part of the text.

Supported keys: printable text, Backspace, Delete, Left/Right, Home/End,
Ctrl-A/B/E/F, Up/Down, Ctrl-P/N (history), Enter, Ctrl-D (EOF on an empty
buffer), and Ctrl-C (cancel input).
Alt-B/F and Ctrl-Left/Right move by words. Ctrl-arrow sequences from xterm
compatible terminals and rxvt are supported. Ctrl-W and Alt-Backspace delete
the preceding word; Alt-D deletes the following word. These use the same word
boundaries: Unicode letters, numbers, combining marks, and underscore belong
to words; punctuation separates them. Home/End and Ctrl-A/E use logical line
boundaries. Ctrl-U/K delete to the beginning/end of the logical line; Ctrl-K
also removes the newline when only whitespace remains. Ctrl-Y reinserts deleted text; consecutive deletion commands
combine their text in order. There is one saved deletion, retained across
queries, rather than a full kill ring.
Up/Down move between screen rows, preserving the preferred terminal column.
At the first/last screen row they navigate history. Ctrl-P/N always navigate
history. Backspace/Delete can join lines by deleting a newline.

Enter inserts a newline when editing an earlier logical line or when the
application's input policy requests more input. Otherwise it submits the
buffer. Alt-Enter always submits. There is no automatic indentation.
Pass an `InputPolicy` subclass as `make_reader(policy=policy)` and override
`more_lines(utf8_text)`. The standalone target uses balanced parentheses;
Pyrolog uses a full-stop token outside quoted text and comments, so floats
and operators such as `=..` do not terminate a query. Terminated syntax errors
reach the normal parser.

Completion, colourization, and bracketed paste are not implemented yet.
Resize is reflected on the next input event, clearing and redrawing the
visible terminal area. Ordinary redraws stay within the editor's area.
Buffers taller than the terminal use a vertical viewport following the cursor.

`make_reader()` returns a Reader, or None when stdin/stdout are not terminals
or the terminal lacks the required capabilities. `Reader.readline(prompt,
continuation_prompt='... ')`
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
type. Cursor positions are byte offsets at code-point boundaries;
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

Ctrl-R and Ctrl-S start incremental reverse and forward history search.
Type a case-sensitive substring; repeat Ctrl-R/Ctrl-S to move between matches,
including occurrences within the same entry. Search includes the current draft
and does not wrap at the ends of history. Backspace removes a code point and
restores the match from before it was typed. A failed search retains the last
match and marks the search prompt. Enter or Escape leaves the match ready to
edit; another Enter accepts it using the normal multiline rules. Other editing
keys leave search and perform their usual action. Ctrl-G or Ctrl-C cancels the
search and restores the original input and cursor. Stored history is unchanged.

Bracketed paste is enabled while editing and disabled before returning control
to the caller. A paste is inserted at the cursor in one operation, including
literal control characters; pasted newlines never submit input. CR, LF and CRLF
are normalized to newlines. Pasting during history search leaves search and
inserts into the displayed match. Invalid UTF-8 rejects the entire paste.
An input EOF before the closing delimiter discards the unfinished paste and
restores the terminal. Terminals without bracketed paste support still send
ordinary key events, so their pasted newlines behave like Enter.

Colour follows the CPython/pyrepl palette. Pyrolog highlights variables in cyan,
quoted text in green, numbers in yellow and comments in red. Prompts are bold
magenta; failed history searches use bold red. Input and saved history stay plain
UTF-8. `Highlighter.gen_colors(text)` supplies ordered `ColorSpan(Span(start,
end), tag)` objects, using half-open byte offsets and semantic theme tags.
Layout applies styles while keeping display widths and cursor mapping separate;
each physical row resets its styles so viewport clipping does not leak colour.

Colour is enabled automatically for terminal output unless `TERM=dumb`.
Presence of `NO_COLOR` disables it, even with an empty value. Otherwise an
internal disabled setting takes precedence over `FORCE_COLOR`, whose presence
forces colour even for non-terminal output or `TERM=dumb`. There is no
application-specific colour environment variable. Unsupported/plain-input
terminals still use the existing fallback rather than enabling the editor.
