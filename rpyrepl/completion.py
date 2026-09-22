"""Completion policy and transient menu state, following pyrepl."""
from rpython.rlib import rutf8
from rpython.rlib.listsort import TimSort
from rpyrepl.layout import clip_prompt, display_width
from rpyrepl.color import THEME, RESET


class Completion(object):
    def __init__(self, start, candidates):
        self.start = start
        self.candidates = candidates


class Completer(object):
    def complete(self, text, pos):
        return Completion(pos, [])


def common_prefix(words):
    first = words[0]
    end = len(first)
    for word in words[1:]:
        i = 0
        while i < end and i < len(word) and first[i] == word[i]:
            i += 1
        end = i
    # Different code points can share leading UTF-8 bytes.
    while end > 0 and end < len(first) and ord(first[end]) & 0xc0 == 0x80:
        end -= 1
    assert end >= 0
    return first[:end]


def same_candidates(left, right):
    if len(left) != len(right):
        return False
    for i in range(len(left)):
        if left[i] != right[i]:
            return False
    return True


class CompletionState(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.active = False
        self.visible = False
        self.message = ''
        self.candidates = []
        self.start = 0
        self.page = 0
        self.next_page = 0

    def complete(self, reader):
        repeated = self.active
        result = reader.completer.complete(reader.buffer, reader.pos)
        start = result.start
        assert 0 <= start <= reader.pos
        stem = reader.buffer[start:reader.pos]
        candidates = []
        seen = {}
        for word in result.candidates:
            rutf8.check_utf8(word, allow_surrogates=False)
            if word.startswith(stem) and word not in seen:
                candidates.append(word)
                seen[word] = True
        TimSort(candidates).sort()
        if not same_candidates(candidates, self.candidates):
            self.page = self.next_page = 0
        self.start = start
        self.candidates = candidates
        self.active = True
        self.message = ''
        if not candidates:
            self.visible = False
            self.message = '[ no matches ]'
            return
        prefix = common_prefix(candidates)
        reader.insert(prefix[len(stem):])
        if len(candidates) == 1:
            self.visible = False
            if repeated:
                self.message = '[ sole completion ]'
        elif repeated:
            self.page = self.next_page if self.visible else 0
            self.visible = True
        else:
            self.message = ('[ complete but not unique ]' if prefix in candidates
                            else '[ not unique ]')

    def filter(self, reader):
        start = self.start
        assert 0 <= start <= reader.pos
        stem = reader.buffer[start:reader.pos]
        self.candidates = [word for word in self.candidates if word.startswith(stem)]
        self.page = self.next_page = 0
        if not self.candidates:
            self.reset()

    def menu(self, width, height):
        # Leave room for the editable cursor row. Prefix every menu row so it
        # remains distinct even with NO_COLOR or truncated candidate labels.
        budget = max(0, height - 1)
        if not budget:
            return []
        limit = max(1, width - 1)
        marker, marker_width = clip_prompt('| ', max(0, limit - 1))
        available = limit - marker_width
        longest = 1
        for word in self.candidates:
            size = 0
            for code in rutf8.Utf8StringIterator(word):
                size += display_width(code)
            longest = max(longest, size)
        cell = min(available, longest + 2)
        columns = max(1, available // cell)
        count = len(self.candidates) - self.page
        needed = (count + columns - 1) // columns
        rows = min(needed, budget)
        more = needed > budget
        if more and budget > 1:
            rows -= 1
        page_count = min(count, rows * columns)
        result = []
        for row in range(rows):
            line = marker
            for column in range(columns):
                index = self.page + column * rows + row
                if index >= self.page + page_count:
                    break
                label, size = clip_prompt(self.candidates[index], max(1, cell - 2))
                line += label + ' ' * (cell - size)
            result.append(line.rstrip())
        self.next_page = self.page + page_count
        if self.next_page >= len(self.candidates):
            self.next_page = 0
        elif more and budget > 1:
            label, size = clip_prompt('| %d more...' % (
                len(self.candidates) - self.next_page), limit)
            result.append(label)
        return result

    def decorate(self, screen, cxy, width, height, colorize):
        x, y = cxy
        assert y >= 0
        if self.visible:
            extra = self.menu(width, height)
            at = y
        elif self.message and height > 1:
            label, size = clip_prompt(self.message, max(1, width - 1))
            extra = [label]
            at = y + 1
        else:
            return screen, cxy
        if colorize:
            extra = [THEME['COMPLETION'] + row + RESET for row in extra]
        result = screen[:at] + extra + screen[at:]
        if self.visible:
            y += len(extra)
        # This presentation-only viewport never enters Layout's cursor map.
        end = y + (2 if self.message else 1)
        start = max(0, end - max(1, height))
        return result[start:start + max(1, height)], (x, y - start)
