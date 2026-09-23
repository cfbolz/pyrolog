"""Unlimited UTF-8 history with append-only persistence."""
import errno
import os
from rpython.rlib import rutf8, rposix
from rpython.rlib.rstring import replace
from rpython.rlib.streamio import open_file_as_stream


class History(object):
    def __init__(self):
        self.entries = []
        self.saved_count = 0

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
        try:
            while True:
                line = stream.readline()
                if not line:
                    break
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

    def save(self, path):
        """Append unsaved entries to the same file used by load().

        Serialize appenders and roll back incomplete entries before unlocking.
        No exit-time rewrite: other sessions' entries stay in the file.
        Applications may catch OSError and continue with in-memory history.
        """
        if self.saved_count == len(self.entries):
            return
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0600)
        try:
            # lockf locks from the current offset (zero on this new fd) through
            # EOF, including later appends. Closing the fd releases the lock.
            while True:
                try:
                    rposix.lockf(fd, rposix.F_LOCK, 0)
                    break
                except OSError as exc:
                    if exc.errno != errno.EINTR:
                        raise
            while self.saved_count < len(self.entries):
                self._append_entry(fd, self.entries[self.saved_count])
                self.saved_count += 1
        finally:
            os.close(fd)

    def _append_entry(self, fd, entry):
        original_size = os.lseek(fd, 0, os.SEEK_END)
        data = replace(entry, '\n', '\r\n') + '\n'
        if original_size:
            os.lseek(fd, max(0, original_size - 2), os.SEEK_SET)
            while True:
                try:
                    tail = os.read(fd, 2)
                    break
                except OSError as exc:
                    if exc.errno != errno.EINTR:
                        raise
            # A bare final line or an unfinished multiline entry needs a
            # separator. Inspect the current file, not this session's snapshot.
            if not tail.endswith('\n') or tail.endswith('\r\n'):
                data = '\n' + data
        try:
            while data:
                try:
                    count = os.write(fd, data)
                except OSError as exc:
                    if exc.errno != errno.EINTR:
                        raise
                else:
                    if count == 0:
                        raise OSError(errno.EIO, 'history write made no progress')
                    data = data[count:]
        except OSError:
            # No cooperating writer can have appended since original_size.
            while True:
                try:
                    os.ftruncate(fd, original_size)
                    break
                except OSError as exc:
                    if exc.errno != errno.EINTR:
                        raise
            raise
