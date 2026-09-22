"""Buffer and editing lifecycle, following pyrepl (see LICENSE).

The initial layout uses one screen row with horizontal scrolling. Buffer and
cursor positions count Unicode code points; terminal I/O uses UTF-8 bytes.
"""
from rpython.rlib.unicodedata import unicodedb_5_2_0 as unicodedb
from rpyrepl.commands import COMMANDS


def char_width(char):
    code = ord(char)
    if unicodedb.combining(code):
        return 0
    if unicodedb.category(code) == 'Cf' and code != 0xad:
        return 0
    if unicodedb.east_asian_width(code) in ('W', 'F'):
        return 2
    return 1


def display_char(char):
    code = ord(char)
    if code < 32:
        return u'^' + unichr(code + 64)
    if code == 127:
        return u'^?'
    return char


def display_width(char):
    return 2 if ord(char) < 32 or ord(char) == 127 else char_width(char)


class Reader(object):
    def __init__(self, console, history=None):
        self.console = console
        self.history = history
        self.history_index = 0
        self.draft = u''
        self.draft_pos = 0
        self.buffer = []
        self.pos = 0
        self.prompt = u''
        self.finished = False
        self.view_start = 0
        self.cxy = (0, 0)

    def insert(self, text):
        pos = self.pos
        assert pos >= 0
        for char in text:
            self.buffer.insert(pos, char)
            pos += 1
        self.pos = pos

    def get_unicode(self):
        return u''.join(self.buffer)

    def move_history(self, direction):
        history = self.history
        if history is None:
            return
        index = self.history_index + direction
        if index < 0 or index > len(history.entries):
            return
        if self.history_index == len(history.entries):
            self.draft = self.get_unicode()
            self.draft_pos = self.pos
        self.history_index = index
        if index == len(history.entries):
            self.buffer = list(self.draft)
            self.pos = self.draft_pos
        else:
            self.buffer = list(history.entries[index])
            self.pos = len(self.buffer)
        self.view_start = 0

    def do_cmd(self, event):
        command = COMMANDS.get(event.evt)
        if command is not None:
            command.do(self, event)

    def calc_screen(self):
        # Reserve the final terminal column to avoid automatic line wrapping.
        limit = max(1, self.console.width - 1)
        prompt = u''
        prompt_width = 0
        for char in self.prompt:
            width = display_width(char)
            if prompt_width + width > max(0, limit - 2):
                break
            prompt += display_char(char)
            prompt_width += width
        available = limit - prompt_width
        start = min(self.view_start, self.pos)
        cursor_width = 0
        for i in range(start, self.pos):
            cursor_width += display_width(self.buffer[i])
        while cursor_width >= available and start < self.pos:
            cursor_width -= display_width(self.buffer[start])
            start += 1
        self.view_start = start
        text = []
        used = 0
        for i in range(start, len(self.buffer)):
            width = display_width(self.buffer[i])
            if used + width > available:
                break
            text.append(display_char(self.buffer[i]))
            used += width
        self.cxy = (prompt_width + cursor_width, 0)
        return [prompt + u''.join(text)]

    def refresh(self):
        screen = self.calc_screen()
        self.console.refresh(screen, self.cxy)

    def readline(self, prompt=u''):
        self.buffer = []
        self.pos = 0
        self.view_start = 0
        self.prompt = prompt
        self.finished = False
        self.history_index = 0
        if self.history is not None:
            self.history_index = len(self.history.entries)
        self.draft = u''
        self.draft_pos = 0
        try:
            self.console.prepare()
            self.refresh()
            while not self.finished:
                self.do_cmd(self.console.get_event())
                if not self.finished:
                    self.refresh()
            self.console.finish()
            return self.get_unicode()
        finally:
            self.console.restore()
