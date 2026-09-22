"""A small RPython line editor, independent of its embedding interpreter."""


class EndOfInput(Exception):
    pass


class CancelledInput(Exception):
    pass


def make_reader(input_fd=0, output_fd=1, history=None, policy=None):
    """Return an interactive reader, or None for plain/unsupported terminals."""
    import os
    if not os.isatty(input_fd) or not os.isatty(output_fd):
        return None
    from rpyrepl.unix_console import UnixConsole, InvalidTerminal
    from rpyrepl.reader import Reader
    try:
        return Reader(UnixConsole(input_fd, output_fd), history, policy)
    except InvalidTerminal:
        return None
