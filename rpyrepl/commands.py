"""Basic editing commands. See LICENSE for the pyrepl attribution."""
from rpyrepl import EndOfInput, CancelledInput
from rpython.rlib import rutf8


class Command(object):
    kills = False

    def do(self, reader, event):
        raise NotImplementedError


class self_insert(Command):
    def do(self, reader, event):
        reader.insert(event.data)


class backspace(Command):
    def do(self, reader, event):
        if reader.pos > 0:
            start = rutf8.prev_codepoint_pos(reader.buffer, reader.pos)
            reader.buffer = reader.buffer[:start] + reader.buffer[reader.pos:]
            reader.pos = start


class delete(Command):
    def do(self, reader, event):
        if reader.pos < len(reader.buffer):
            end = rutf8.next_codepoint_pos(reader.buffer, reader.pos)
            reader.buffer = reader.buffer[:reader.pos] + reader.buffer[end:]


class eof(delete):
    def do(self, reader, event):
        if not reader.buffer:
            raise EndOfInput
        delete.do(self, reader, event)


class left(Command):
    def do(self, reader, event):
        if reader.pos > 0:
            reader.pos = rutf8.prev_codepoint_pos(reader.buffer, reader.pos)


class right(Command):
    def do(self, reader, event):
        if reader.pos < len(reader.buffer):
            reader.pos = rutf8.next_codepoint_pos(reader.buffer, reader.pos)


class beginning_of_line(Command):
    def do(self, reader, event):
        reader.pos = 0


class end_of_line(Command):
    def do(self, reader, event):
        reader.pos = len(reader.buffer)


class backward_word(Command):
    def do(self, reader, event):
        reader.pos = reader.bow()


class forward_word(Command):
    def do(self, reader, event):
        reader.pos = reader.eow()


class KillCommand(Command):
    kills = True


class backward_kill_word(KillCommand):
    def do(self, reader, event):
        reader.kill_range(reader.bow(), reader.pos)


class kill_word(KillCommand):
    def do(self, reader, event):
        reader.kill_range(reader.pos, reader.eow())


class unix_line_discard(KillCommand):
    def do(self, reader, event):
        reader.kill_range(0, reader.pos)


class kill_line(KillCommand):
    def do(self, reader, event):
        reader.kill_range(reader.pos, len(reader.buffer))


class yank(Command):
    def do(self, reader, event):
        reader.insert(reader.kill_buffer)


class accept(Command):
    def do(self, reader, event):
        reader.finished = True


class previous_history(Command):
    def do(self, reader, event):
        reader.move_history(-1)


class next_history(Command):
    def do(self, reader, event):
        reader.move_history(1)


class cancel(Command):
    def do(self, reader, event):
        raise CancelledInput


# These immutable command instances keep runtime dispatch statically typed.
COMMANDS = {
    'text': self_insert(), 'backspace': backspace(), 'delete': delete(),
    'eof': eof(), 'left': left(), 'right': right(),
    'home': beginning_of_line(), 'end': end_of_line(),
    'accept': accept(), 'cancel': cancel(),
    'up': previous_history(), 'down': next_history(),
    'backward-word': backward_word(), 'forward-word': forward_word(),
    'backward-kill-word': backward_kill_word(), 'kill-word': kill_word(),
    'unix-line-discard': unix_line_discard(), 'kill-line': kill_line(),
    'yank': yank(),
}
