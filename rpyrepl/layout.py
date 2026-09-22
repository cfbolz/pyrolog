"""UTF-8 buffer offsets mapped to terminal rows and columns."""
from rpython.rlib import rutf8
from rpython.rlib.unicodedata import unicodedb_15_0_0 as unicodedb


def char_width(code):
    if unicodedb.combining(code):
        return 0
    if unicodedb.category(code) == 'Cf' and code != 0xad:
        return 0
    if unicodedb.east_asian_width(code) in ('W', 'F'):
        return 2
    return 1


def display_width(code):
    return 2 if code < 32 or code == 127 else char_width(code)


def display_char(text, pos, end, code):
    if code < 32:
        return '^' + chr(code + 64)
    if code == 127:
        return '^?'
    return text[pos:end]


def clip_prompt(prompt, limit):
    rendered = ''
    column = 0
    for code, pos in rutf8.Utf8StringPosIterator(prompt):
        width = display_width(code)
        if column + width > limit:
            break
        end = rutf8.next_codepoint_pos(prompt, pos)
        rendered += display_char(prompt, pos, end, code)
        column += width
    return rendered, column


class Row(object):
    def __init__(self, prompt, column, start):
        self.text = prompt
        self.positions = [start]
        self.columns = [column]
        self.wrapped = False


class Layout(object):
    def __init__(self, text, width, prompt, continuation_prompt):
        self.rows = []
        self.screen = []
        limit = max(1, width - 1)
        prefix, column = clip_prompt(prompt, max(0, limit - 2))
        row = Row(prefix, column, 0)
        self.rows.append(row)
        pos = 0
        while pos < len(text):
            code = rutf8.codepoint_at_pos(text, pos)
            end = rutf8.next_codepoint_pos(text, pos)
            if code == 10:
                prefix, column = clip_prompt(continuation_prompt, max(0, limit - 2))
                row = Row(prefix, column, end)
                self.rows.append(row)
            else:
                size = display_width(code)
                rendered = display_char(text, pos, end, code)
                # Even a terminal narrower than a wide character must progress.
                if size > limit:
                    size, rendered = 1, '?'
                if column + size > limit:
                    row.wrapped = True
                    if width > 1:
                        row.text += '\\'
                    row = Row('', 0, pos)
                    self.rows.append(row)
                    column = 0
                row.text += rendered
                column += size
                row.positions.append(end)
                row.columns.append(column)
            pos = end
        for row in self.rows:
            self.screen.append(row.text)

    def pos_to_xy(self, pos):
        for y in range(len(self.rows)):
            row = self.rows[y]
            if row.wrapped and pos == row.positions[-1]:
                continue
            for i in range(len(row.positions)):
                if row.positions[i] == pos:
                    return row.columns[i], y
        raise AssertionError('cursor is not at a UTF-8 boundary')

    def xy_to_pos(self, x, y):
        row = self.rows[y]
        last = len(row.positions) - 1
        if row.wrapped:
            # The final boundary belongs to the start of the following row.
            last = max(0, last - 1)
        index = 0
        for i in range(1, last + 1):
            if row.columns[i] > x:
                break
            index = i
        return row.positions[index]
