"""Basic editing commands. See LICENSE for the pyrepl attribution."""
from rpyrepl import EndOfInput, CancelledInput


class Command(object):
    def do(self, reader, event):
        raise NotImplementedError


class self_insert(Command):
    def do(self, reader, event):
        reader.insert(event.data)


class backspace(Command):
    def do(self, reader, event):
        if reader.pos > 0:
            reader.pos -= 1
            del reader.buffer[reader.pos]


class delete(Command):
    def do(self, reader, event):
        if reader.pos < len(reader.buffer):
            del reader.buffer[reader.pos]


class eof(delete):
    def do(self, reader, event):
        if not reader.buffer:
            raise EndOfInput
        delete.do(self, reader, event)


class left(Command):
    def do(self, reader, event):
        if reader.pos > 0:
            reader.pos -= 1


class right(Command):
    def do(self, reader, event):
        if reader.pos < len(reader.buffer):
            reader.pos += 1


class beginning_of_line(Command):
    def do(self, reader, event):
        reader.pos = 0


class end_of_line(Command):
    def do(self, reader, event):
        reader.pos = len(reader.buffer)


class accept(Command):
    def do(self, reader, event):
        reader.finished = True


class cancel(Command):
    def do(self, reader, event):
        raise CancelledInput


# These immutable command instances keep runtime dispatch statically typed.
COMMANDS = {
    'text': self_insert(), 'backspace': backspace(), 'delete': delete(),
    'eof': eof(), 'left': left(), 'right': right(),
    'home': beginning_of_line(), 'end': end_of_line(),
    'accept': accept(), 'cancel': cancel(),
}
