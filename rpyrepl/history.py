"""Bounded UTF-8 history storage; applications decide what to record."""
from rpython.rlib import rutf8


class History(object):
    def __init__(self, limit=1000):
        assert limit > 0
        self.limit = limit
        self.entries = []

    def append(self, text):
        rutf8.check_utf8(text, allow_surrogates=False)
        if len(self.entries) == self.limit:
            del self.entries[0]
        self.entries.append(text)
