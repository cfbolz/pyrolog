"""Bounded Unicode history storage; applications decide what to record."""


class History(object):
    def __init__(self, limit=1000):
        assert limit > 0
        self.limit = limit
        self.entries = []

    def append(self, text):
        if len(self.entries) == self.limit:
            del self.entries[0]
        self.entries.append(text)
