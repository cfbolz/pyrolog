"""Unlimited UTF-8 history with append-only persistence."""
import errno
import os
from rpython.rlib import rutf8
from rpython.rlib.rstring import replace
from rpython.rlib.streamio import open_file_as_stream


class History(object):
    def __init__(self):
        self.entries = []
        self.saved_count = 0
        self.needs_separator = False
        self.pending_write = ''

    def append(self, text):
        rutf8.check_utf8(text, allow_surrogates=False)
        self.entries.append(text)

    def load(self, path):
        """Load a history file before recording new entries.

        Like pyrepl, LF ends an entry and CRLF continues a multiline entry.
        Malformed UTF-8 entries are skipped; missing files raise OSError.
        """
        stream = open_file_as_stream(path, 'rb')
        parts = []
        loaded = []
        needs_separator = False
        try:
            while True:
                line = stream.readline()
                if not line:
                    break
                needs_separator = not line.endswith('\n')
                if line.endswith('\r\n'):
                    end = len(line) - 2
                    assert end >= 0
                    parts.append(line[:end] + '\n')
                    continue
                if line.endswith('\n'):
                    end = len(line) - 1
                    assert end >= 0
                    line = line[:end]
                parts.append(line)
                entry = ''.join(parts)
                parts = []
                if entry:
                    try:
                        rutf8.check_utf8(entry, allow_surrogates=False)
                    except rutf8.CheckError:
                        pass
                    else:
                        loaded.append(entry)
        finally:
            stream.close()
        self.entries.extend(loaded)
        self.saved_count = len(self.entries)
        self.needs_separator = needs_separator or bool(parts)

    def save(self, path):
        """Append unsaved entries to the same file used by load().

        No exit-time rewrite: other sessions' entries stay in the file.
        Applications may catch OSError and continue with in-memory history.
        """
        if self.saved_count == len(self.entries):
            return
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0600)
        try:
            while self.saved_count < len(self.entries):
                if not self.pending_write:
                    data = replace(self.entries[self.saved_count], '\n', '\r\n') + '\n'
                    if self.needs_separator:
                        data = '\n' + data
                    self.pending_write = data
                # Preserve the unwritten suffix across failures: replaying the
                # whole entry would duplicate its already-written prefix.
                while self.pending_write:
                    try:
                        count = os.write(fd, self.pending_write)
                    except OSError as exc:
                        if exc.errno != errno.EINTR:
                            raise
                    else:
                        if count == 0:
                            raise OSError(errno.EIO, 'history write made no progress')
                        self.pending_write = self.pending_write[count:]
                self.saved_count += 1
                self.needs_separator = False
        finally:
            os.close(fd)
