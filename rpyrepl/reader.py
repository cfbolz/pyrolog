"""Buffer and editing lifecycle, following pyrepl (see LICENSE).

Logical lines wrap into screen rows. Text is
valid UTF-8; buffer positions are byte offsets at code-point boundaries.
Screen coordinates count terminal columns, independently of byte offsets.
"""
from rpython.rlib import rutf8
from rpython.rlib.unicodedata import unicodedb_15_0_0 as unicodedb
from rpyrepl.commands import COMMANDS
from rpyrepl.layout import Layout
from rpyrepl.policy import InputPolicy
from rpyrepl import EndOfInput, CancelledInput


def is_word(code):
    # Keep identifiers and decomposed accents together without language syntax.
    return code == 95 or unicodedb.isalnum(code) or unicodedb.category(code).startswith('M')


class Reader(object):
    def __init__(self, console, history=None, policy=None):
        self.console = console
        self.policy = policy if policy is not None else InputPolicy()
        self.continuation_prompt = '... '
        self.preferred_column = -1
        self.history = history
        self.history_index = 0
        self.draft = ''
        self.draft_pos = 0
        self.buffer = ''
        self.pos = 0
        self.prompt = ''
        self.finished = False
        self.cxy = (0, 0)
        self.kill_buffer = ''
        self.last_command_was_kill = False
        self.search = None

    def insert(self, text):
        rutf8.check_utf8(text, allow_surrogates=False)
        pos = self.pos
        assert pos >= 0
        self.buffer = self.buffer[:pos] + text + self.buffer[pos:]
        self.pos = pos + len(text)

    def get_utf8(self):
        return self.buffer

    def word_at(self, pos):
        return is_word(rutf8.codepoint_at_pos(self.buffer, pos))

    def bow(self):
        pos = self.pos
        while pos > 0:
            previous = rutf8.prev_codepoint_pos(self.buffer, pos)
            if self.word_at(previous):
                break
            pos = previous
        while pos > 0:
            previous = rutf8.prev_codepoint_pos(self.buffer, pos)
            if not self.word_at(previous):
                break
            pos = previous
        return pos

    def eow(self):
        pos = self.pos
        while pos < len(self.buffer) and not self.word_at(pos):
            pos = rutf8.next_codepoint_pos(self.buffer, pos)
        while pos < len(self.buffer) and self.word_at(pos):
            pos = rutf8.next_codepoint_pos(self.buffer, pos)
        return pos

    def kill_range(self, start, end):
        assert 0 <= start <= end <= len(self.buffer)
        if start == end:
            return
        killed = self.buffer[start:end]
        if not self.last_command_was_kill:
            self.kill_buffer = killed
        elif end <= self.pos:
            self.kill_buffer = killed + self.kill_buffer
        else:
            self.kill_buffer += killed
        self.buffer = self.buffer[:start] + self.buffer[end:]
        self.pos = start

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

    def do_cmd(self, event):
        if self.search is not None:
            if self.search.handle(self, event):
                return
        command = COMMANDS.get(event.evt)
        if command is not None:
            if not command.vertical:
                self.preferred_column = -1
            command.do(self, event)
            self.last_command_was_kill = command.kills
        else:
            self.last_command_was_kill = False

    def get_layout(self):
        if self.search is not None:
            prompt = self.search.prompt()
            return Layout(self.buffer, self.console.width, prompt, prompt)
        return Layout(self.buffer, self.console.width, self.prompt,
                      self.continuation_prompt)

    def calc_screen(self):
        layout = self.get_layout()
        self.cxy = layout.pos_to_xy(self.pos)
        return layout.screen

    def bol(self):
        pos = self.buffer.rfind('\n', 0, self.pos) + 1
        assert pos >= 0
        return pos

    def eol(self):
        end = self.buffer.find('\n', self.pos)
        return len(self.buffer) if end < 0 else end

    def move_vertical(self, direction):
        layout = self.get_layout()
        x, y = layout.pos_to_xy(self.pos)
        new_y = y + direction
        if new_y < 0 or new_y >= len(layout.rows):
            self.move_history(direction)
            self.preferred_column = -1
            return
        if self.preferred_column < 0:
            self.preferred_column = x
        self.pos = layout.xy_to_pos(self.preferred_column, new_y)

    def maybe_accept(self):
        if self.buffer.find('\n', self.pos) >= 0 or self.policy.more_lines(self.buffer):
            self.insert('\n')
        else:
            self.finished = True

    def refresh(self):
        screen = self.calc_screen()
        self.console.refresh(screen, self.cxy)

    def readline(self, prompt='', continuation_prompt='... '):
        rutf8.check_utf8(prompt, allow_surrogates=False)
        self.buffer = ''
        self.pos = 0
        self.prompt = prompt
        rutf8.check_utf8(continuation_prompt, allow_surrogates=False)
        self.continuation_prompt = continuation_prompt
        self.preferred_column = -1
        self.finished = False
        self.search = None
        self.last_command_was_kill = False
        self.history_index = 0
        if self.history is not None:
            self.history_index = len(self.history.entries)
        self.draft = ''
        self.draft_pos = 0
        try:
            self.console.prepare()
            self.refresh()
            try:
                while not self.finished:
                    self.do_cmd(self.console.get_event())
                    if not self.finished:
                        self.refresh()
            except (EndOfInput, CancelledInput):
                self.console.finish()
                raise
            self.console.finish()
            return self.get_utf8()
        finally:
            self.console.restore()
