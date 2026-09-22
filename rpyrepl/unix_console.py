"""Unix terminal backend with scoped terminal modes and a vertical viewport."""
import errno
import os
from rpython.rlib import rtermios, rpoll, rposix, rutf8
from rpython.rtyper.lltypesystem import lltype, rffi
from rpyrepl import EndOfInput
from rpyrepl.console import Console, Event
from rpyrepl.color import can_colorize
from rpyrepl.terminfo import InvalidTerminal, setupterm, tigetstr


class TermState(object):
    def __init__(self, fd):
        self.attrs = rtermios.tcgetattr(fd)


class UnixConsole(Console):
    def __init__(self, input_fd=0, output_fd=1):
        self.input_fd = input_fd
        self.output_fd = output_fd
        self.can_colorize = can_colorize(output_fd)
        self.saved = None
        self.bracketed_paste = False
        self.pending_byte = ''
        name = os.environ.get('TERM')
        if not name or name == 'dumb':
            raise InvalidTerminal
        setupterm(name, output_fd)
        self.cr = tigetstr('cr', True)
        self.el = tigetstr('el', True)
        self.right = tigetstr('cuf1', True)
        self.up = tigetstr('cuu1', True)
        self.down = tigetstr('cud1', True)
        self.clear = tigetstr('clear', True)
        self.keycodes = {'\x1b[D': 'left', '\x1b[C': 'right',
                         '\x1b[A': 'up', '\x1b[B': 'down',
                         '\x1b[H': 'home', '\x1b[F': 'end',
                         '\x1b[3~': 'delete',
                         '\x1bb': 'backward-word', '\x1bf': 'forward-word',
                         '\x1bd': 'kill-word',
                         '\x1b\x7f': 'backward-kill-word',
                         '\x1b\x08': 'backward-kill-word',
                         # Ctrl-arrows: xterm-compatible terminals and rxvt.
                         '\x1b[1;5D': 'backward-word',
                         '\x1b[1;5C': 'forward-word',
                         '\x1bOd': 'backward-word', '\x1bOc': 'forward-word'}
        self.keycodes['\x1b\r'] = 'force-accept'
        self.keycodes['\x1b\n'] = 'force-accept'
        self.keycodes['\x1b[200~'] = 'paste'
        for capability, command in [('kcub1', 'left'), ('kcuf1', 'right'),
                                    ('kcuu1', 'up'), ('kcud1', 'down'),
                                    ('khome', 'home'), ('kend', 'end'),
                                    ('kdch1', 'delete')]:
            sequence = tigetstr(capability)
            if sequence:
                self.keycodes[sequence] = command
        self.erase = '\x7f'
        self.width = 80
        self.height = 24
        self.reset_display()

    def reset_display(self):
        self.rendered_rows = 0
        self.cursor_y = 0
        self.offset = 0
        self.last_width = self.width
        self.last_height = self.height

    def getwidth(self):
        with lltype.scoped_alloc(rposix.WINSIZE) as size:
            result = rposix.c_ioctl_voidp(self.output_fd, rtermios.TIOCGWINSZ,
                                         rffi.cast(rffi.VOIDP, size))
            width = rffi.cast(lltype.Signed, size.c_ws_col)
            height = rffi.cast(lltype.Signed, size.c_ws_row)
            if result == 0 and height > 0:
                self.height = height
            if result == 0 and width > 0:
                return width
        return 80

    def prepare(self):
        saved = TermState(self.input_fd)
        self.saved = saved
        iflag, oflag, cflag, lflag, ispeed, ospeed, cc = saved.attrs
        self.erase = cc[rtermios.VERASE]
        cc = cc[:]
        cc[rtermios.VMIN] = '\x01'
        cc[rtermios.VTIME] = '\x00'
        # Ctrl-C is an editor command here. Restore ISIG before executing code.
        lflag &= ~(rtermios.ICANON | rtermios.ECHO | rtermios.IEXTEN | rtermios.ISIG)
        iflag &= ~(rtermios.IXON | rtermios.ISTRIP | rtermios.INPCK |
                   rtermios.ICRNL | rtermios.INLCR | rtermios.IGNCR)
        rtermios.tcsetattr(self.input_fd, rtermios.TCSANOW,
                          (iflag, oflag, cflag, lflag, ispeed, ospeed, cc))
        self.width = self.getwidth()
        self.reset_display()
        # Set this before writing so restore also handles a partial write.
        self.bracketed_paste = True
        self.write('\x1b[?2004h')

    def restore(self):
        try:
            if self.bracketed_paste:
                self.bracketed_paste = False
                self.write('\x1b[?2004l')
        finally:
            if self.saved is not None:
                rtermios.tcsetattr(self.input_fd, rtermios.TCSANOW, self.saved.attrs)
                self.saved = None

    def write(self, text):
        while text:
            try:
                count = os.write(self.output_fd, text)
            except OSError as exc:
                if exc.errno != errno.EINTR:
                    raise
            else:
                if count == 0:
                    raise OSError(errno.EIO, 'terminal write made no progress')
                text = text[count:]

    def refresh(self, screen, cxy):
        if self.width != self.last_width or self.height != self.last_height:
            # Terminal reflow makes the previous physical origin unreliable.
            self.write(self.clear)
            self.reset_display()
        height = max(1, self.height)
        x, y = cxy
        assert x >= 0 and 0 <= y < len(screen)
        offset = self.offset
        if y < offset:
            offset = y
        elif y >= offset + height:
            offset = y - height + 1
        offset = min(offset, max(0, len(screen) - height))
        assert offset >= 0
        visible = screen[offset:offset + height]
        rows = max(self.rendered_rows, len(visible))
        self.write(self.cr + self.up * self.cursor_y)
        for i in range(rows):
            if i:
                self.write('\r\n')
            self.write(self.el)
            if i < len(visible):
                self.write(visible[i])
            # Cancel delayed automatic wrapping after a full-width row.
            self.write(self.cr)
        self.cursor_y = y - offset
        self.write(self.up * (rows - 1 - self.cursor_y) +
                   self.right * min(x, max(0, self.width - 1)))
        self.rendered_rows = len(visible)
        self.offset = offset

    def finish(self):
        self.write(self.cr + self.down * max(0, self.rendered_rows - 1 - self.cursor_y)
                   + '\r\n')

    def read_byte(self):
        if self.pending_byte:
            char = self.pending_byte
            self.pending_byte = ''
            return char
        while True:
            try:
                char = os.read(self.input_fd, 1)
            except OSError as exc:
                if exc.errno != errno.EINTR:
                    raise
            else:
                if not char:
                    raise EndOfInput
                return char

    def read_escape(self):
        sequence = '\x1b'
        while len(sequence) < 32:
            try:
                ready = rpoll.poll({self.input_fd: rpoll.POLLIN}, 50)
            except rpoll.PollError as exc:
                if exc.errno == errno.EINTR:
                    continue
                raise OSError(exc.errno, 'terminal poll failed')
            if not ready:
                return Event('escape') if sequence == '\x1b' else Event('unknown')
            sequence += self.read_byte()
            command = self.keycodes.get(sequence)
            if command is not None:
                if command == 'paste':
                    return self.read_paste()
                return Event(command)
            prefix = False
            for key in self.keycodes:
                if key.startswith(sequence):
                    prefix = True
                    break
            if not prefix:
                # Consume unknown CSI sequences so their suffix is not inserted.
                if sequence.startswith('\x1b[') and not ('@' <= sequence[-1] <= '~'):
                    continue
                return Event('unknown')
        return Event('unknown')

    def read_paste(self):
        # No escape timeout within a paste: even its closing delimiter may
        # arrive across reads. Keep only a bounded delimiter prefix pending.
        end = '\x1b[201~'
        pending = ''
        parts = []
        after_cr = False
        while True:
            pending += self.read_byte()
            if pending == end:
                break
            while not end.startswith(pending):
                char = pending[0]
                pending = pending[1:]
                # Normalize terminal CR, LF and clipboard CRLF to one newline.
                if char == '\r':
                    parts.append('\n')
                elif char != '\n' or not after_cr:
                    parts.append(char)
                after_cr = char == '\r'
        text = ''.join(parts)
        try:
            rutf8.check_utf8(text, allow_surrogates=False)
        except rutf8.CheckError:
            # Reject the whole paste without interpreting any of it as keys.
            return Event('unknown')
        return Event('paste', text)

    def get_event(self):
        char = self.read_byte()
        self.width = self.getwidth()
        if char in ('\r', '\n'):
            return Event('accept')
        if char == self.erase or char in ('\x08', '\x7f'):
            return Event('backspace')
        if char == '\x04':
            return Event('eof')
        if char == '\x03':
            return Event('cancel')
        if char == '\x02':
            return Event('left')
        if char == '\x06':
            return Event('right')
        if char == '\x01':
            return Event('home')
        if char == '\x05':
            return Event('end')
        if char == '\x10':
            return Event('previous-history')
        if char == '\x0e':
            return Event('next-history')
        if char == '\x17':
            return Event('backward-kill-word')
        if char == '\x15':
            return Event('unix-line-discard')
        if char == '\x0b':
            return Event('kill-line')
        if char == '\x19':
            return Event('yank')
        if char == '\x12':
            return Event('reverse-search')
        if char == '\x13':
            return Event('forward-search')
        if char == '\x07':
            return Event('abort-search')
        if char == '\x1b':
            return self.read_escape()
        first = ord(char[0])
        if first < 32:
            return Event('unknown')
        count = 1
        if 0xc2 <= first <= 0xdf:
            count = 2
        elif 0xe0 <= first <= 0xef:
            count = 3
        elif 0xf0 <= first <= 0xf4:
            count = 4
        elif first >= 128:
            return Event('unknown')
        for i in range(count - 1):
            following = self.read_byte()
            if not 0x80 <= ord(following[0]) <= 0xbf:
                self.pending_byte = following
                return Event('unknown')
            char += following
        try:
            rutf8.check_utf8(char, allow_surrogates=False)
        except rutf8.CheckError:
            return Event('unknown')
        return Event('text', char)
