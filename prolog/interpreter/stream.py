from rpython.rlib.streamio import fdopen_as_stream
from prolog.interpreter.term import NonVar
from prolog.interpreter.error import UnificationFailed

class StreamWrapper(object):
    def __init__(self):
        # XXX use 0 and 1 instead of sys.stdin.fileno() and sys.stdout.fileno()
        # because otherwise problems at testing occur
        self.current_instream = PrologInputStream(fdopen_as_stream(0, "r", False))
        self.current_outstream = PrologOutputStream(fdopen_as_stream(1, "w", False))
        self.streams = {self.current_instream.fd(): self.current_instream,
                        self.current_outstream.fd(): self.current_outstream}
        self.aliases = {self.current_instream.alias: self.current_instream,
                        self.current_outstream.alias: self.current_outstream}

class PrologStream(object):
    def __init__(self, stream, binary=False):
        self.stream = stream
        self.binary = binary
        self.alias = "$stream_%d" % self.fd()

    def fd(self):   
        return self.stream.try_to_find_file_descriptor()

    def seek(self, offset, how):
        self.stream.seek(offset, how)

    def close(self):
        self.stream.close()

    def tell(self):
        return self.stream.tell()

class PrologInputStream(PrologStream):
    def __init__(self, stream, binary=False):
        PrologStream.__init__(self, stream, binary)
        self.pending = ''

    def read(self, n):
        if self.pending:
            result = self.pending[:n]
            self.pending = self.pending[len(result):]
            if len(result) == n:
                return result
            return result + self.stream.read(n - len(result))
        if self.fd() == 0:
            s = fdopen_as_stream(1, "w", False)
            s.write("|: ")
        return self.stream.read(n)

    def unread(self, data):
        self.pending = data + self.pending

    def tell(self):
        return self.stream.tell() - len(self.pending)

    def seek(self, offset, how):
        if how == 1:
            offset -= len(self.pending)
        self.stream.seek(offset, how)
        self.pending = ''

class PrologOutputStream(PrologStream):
    def __init__(self, fd, binary=False):
        PrologStream.__init__(self, fd, binary)

    def write(self, data):
        self.stream.write(data)
