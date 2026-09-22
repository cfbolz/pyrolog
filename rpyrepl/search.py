"""Incremental substring search over immutable history entries and the draft."""
from rpython.rlib import rutf8


class SearchState(object):
    def __init__(self, reader, direction):
        self.original_buffer = reader.buffer
        self.original_pos = reader.pos
        self.original_index = reader.history_index
        self.original_draft = reader.draft
        self.original_draft_pos = reader.draft_pos
        self.index = reader.history_index
        self.pos = reader.pos
        self.direction = direction
        self.term = ''
        self.failed = False
        self.undo = []

    def count(self, reader):
        return len(reader.history.entries) if reader.history is not None else 0

    def entry(self, reader, index):
        if index == self.original_index:
            return self.original_buffer
        if index == self.count(reader):
            return self.original_draft
        assert reader.history is not None
        return reader.history.entries[index]

    def select(self, reader, index, pos):
        assert index >= 0 and pos >= 0
        self.index, self.pos = index, pos
        reader.buffer = self.entry(reader, index)
        reader.pos = pos
        reader.history_index = index
        if self.original_index == self.count(reader):
            reader.draft = self.original_buffer
            reader.draft_pos = self.original_pos

    def find(self, reader, include_current):
        index, pos = self.index, self.pos
        count = self.count(reader)
        if not self.term:
            index += self.direction
            if 0 <= index <= count:
                text = self.entry(reader, index)
                self.select(reader, index, len(text) if self.direction < 0 else 0)
                self.failed = False
            else:
                self.failed = True
            return
        while 0 <= index <= count:
            text = self.entry(reader, index)
            if self.direction < 0:
                end = min(len(text), max(0, pos + len(self.term) -
                                        (0 if include_current else 1)))
                match = text.rfind(self.term, 0, end)
            else:
                start = max(0, pos + (0 if include_current else 1))
                match = text.find(self.term, start)
            if match >= 0:
                self.select(reader, index, match)
                self.failed = False
                return
            index += self.direction
            if 0 <= index <= count:
                pos = len(self.entry(reader, index)) if self.direction < 0 else 0
            include_current = True
        self.failed = True

    def add(self, reader, text):
        rutf8.check_utf8(text, allow_surrogates=False)
        pos = 0
        while pos < len(text):
            end = rutf8.next_codepoint_pos(text, pos)
            self.undo.append((self.index, self.pos, self.failed))
            self.term += text[pos:end]
            self.find(reader, True)
            pos = end

    def backspace(self, reader):
        if self.term:
            end = rutf8.prev_codepoint_pos(self.term, len(self.term))
            self.term = self.term[:end]
            index, pos, failed = self.undo.pop()
            self.select(reader, index, pos)
            self.failed = failed

    def cancel(self, reader):
        reader.buffer = self.original_buffer
        reader.pos = self.original_pos
        reader.history_index = self.original_index
        reader.draft = self.original_draft
        reader.draft_pos = self.original_draft_pos
        reader.search = None

    def handle(self, reader, event):
        name = event.evt
        if name == 'text':
            self.add(reader, event.data)
        elif name == 'backspace':
            self.backspace(reader)
        elif name == 'reverse-search' or name == 'forward-search':
            self.direction = -1 if name == 'reverse-search' else 1
            self.find(reader, False)
        elif name == 'cancel' or name == 'abort-search':
            self.cancel(reader)
        elif name == 'unknown':
            pass
        else:
            reader.search = None
            # Enter keeps the match ready to edit; other editing keys also act.
            return name in ('accept', 'force-accept', 'escape')
        return True

    def prompt(self):
        direction = 'r-search' if self.direction < 0 else 'f-search'
        if self.failed:
            direction = 'failed ' + direction
        return '(' + direction + ' ' + self.term + ') '
