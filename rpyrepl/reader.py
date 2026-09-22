"""Buffer and editing lifecycle, following pyrepl (see LICENSE).

The initial layout uses one screen row with horizontal scrolling. Text is
valid UTF-8; buffer positions are byte offsets at code-point boundaries.
Screen coordinates count terminal columns, independently of byte offsets.
"""
from rpython.rlib import rutf8
from rpython.rlib.unicodedata import unicodedb_5_2_0 as unicodedb
from rpyrepl.commands import COMMANDS


def char_width(code):
    if unicodedb.combining(code):
        return 0
    if unicodedb.category(code) == 'Cf' and code != 0xad:
        return 0
    if unicodedb.east_asian_width(code) in ('W', 'F'):
        return 2
    return 1


def display_char(text, pos, end, code):
    if code < 32:
        return '^' + chr(code + 64)
    if code == 127:
        return '^?'
    return text[pos:end]


def display_width(code):
    return 2 if code < 32 or code == 127 else char_width(code)


class Reader(object):
    def __init__(self, console, history=None):
        self.console = console
        self.history = history
        self.history_index = 0
        self.draft = ''
        self.draft_pos = 0
        self.buffer = ''
        self.pos = 0
        self.prompt = ''
        self.finished = False
        self.view_start = 0
        self.cxy = (0, 0)

    def insert(self, text):
        rutf8.check_utf8(text, allow_surrogates=False)
        pos = self.pos
        assert pos >= 0
        self.buffer = self.buffer[:pos] + text + self.buffer[pos:]
        self.pos = pos + len(text)

    def get_utf8(self):
        return self.buffer

    def move_history(self, direction):
        history = self.history
        if history is None:
            return
        index = self.history_index + direction
        if index < 0 or index > len(history.entries):
            return
        if self.history_index == len(history.entries):
            self.draft = self.get_utf8()
            self.draft_pos = self.pos
        self.history_index = index
        if index == len(history.entries):
            self.buffer = self.draft
            self.pos = self.draft_pos
        else:
            self.buffer = history.entries[index]
            self.pos = len(self.buffer)
        self.view_start = 0

    def do_cmd(self, event):
        command = COMMANDS.get(event.evt)
        if command is not None:
            command.do(self, event)

    def calc_screen(self):
        # Reserve the final terminal column to avoid automatic line wrapping.
        limit = max(1, self.console.width - 1)
        prompt = ''
        prompt_width = 0
        pos = 0
        while pos < len(self.prompt):
            code = rutf8.codepoint_at_pos(self.prompt, pos)
            end = rutf8.next_codepoint_pos(self.prompt, pos)
            width = display_width(code)
            if prompt_width + width > max(0, limit - 2):
                break
            prompt += display_char(self.prompt, pos, end, code)
            prompt_width += width
            pos = end
        available = limit - prompt_width
        start = min(self.view_start, self.pos)
        cursor_width = 0
        pos = start
        while pos < self.pos:
            cursor_width += display_width(rutf8.codepoint_at_pos(self.buffer, pos))
            pos = rutf8.next_codepoint_pos(self.buffer, pos)
        while cursor_width >= available and start < self.pos:
            cursor_width -= display_width(rutf8.codepoint_at_pos(self.buffer, start))
            start = rutf8.next_codepoint_pos(self.buffer, start)
        self.view_start = start
        text = []
        used = 0
        pos = start
        while pos < len(self.buffer):
            code = rutf8.codepoint_at_pos(self.buffer, pos)
            end = rutf8.next_codepoint_pos(self.buffer, pos)
            width = display_width(code)
            if used + width > available:
                break
            text.append(display_char(self.buffer, pos, end, code))
            used += width
            pos = end
        self.cxy = (prompt_width + cursor_width, 0)
        return [prompt + ''.join(text)]

    def refresh(self):
        screen = self.calc_screen()
        self.console.refresh(screen, self.cxy)

    def readline(self, prompt=''):
        rutf8.check_utf8(prompt, allow_surrogates=False)
        self.buffer = ''
        self.pos = 0
        self.view_start = 0
        self.prompt = prompt
        self.finished = False
        self.history_index = 0
        if self.history is not None:
            self.history_index = len(self.history.entries)
        self.draft = ''
        self.draft_pos = 0
        try:
            self.console.prepare()
            self.refresh()
            while not self.finished:
                self.do_cmd(self.console.get_event())
                if not self.finished:
                    self.refresh()
            self.console.finish()
            return self.get_utf8()
        finally:
            self.console.restore()
