"""CPython/pyrepl palette and environment policy, adapted for output fds."""
import os

BOLD = '\x1b[1m'
BOLD_BLUE = '\x1b[1;34m'
BOLD_MAGENTA = '\x1b[1;35m'
BOLD_RED = '\x1b[1;31m'
BOLD_GREEN = '\x1b[1;32m'
BOLD_YELLOW = '\x1b[1;33m'
BOLD_GREEN_UNDERLINE = '\x1b[1;4;32m'
BOLD_RED_UNDERLINE = '\x1b[1;4;31m'
CYAN = '\x1b[36m'
GREEN = '\x1b[32m'
MAGENTA = '\x1b[35m'
RED = '\x1b[31m'
YELLOW = '\x1b[33m'
RESET = '\x1b[0m'

THEME = {
    'PROMPT': BOLD_MAGENTA,
    'KEYWORD': BOLD_BLUE,
    'KEYWORD_CONSTANT': BOLD_BLUE,
    'SOFT_KEYWORD': BOLD_BLUE,
    'BUILTIN': CYAN,
    'COMMENT': RED,
    'STRING': GREEN,
    'NUMBER': YELLOW,
    'OP': RESET,
    'DEFINITION': BOLD,
    # Prolog-specific roles, using the same palette.
    'VARIABLE': CYAN,
    'SEARCH_FAILURE': BOLD_RED,
    'MATCHING_DELIMITER': BOLD_GREEN_UNDERLINE,
    'MISMATCHED_DELIMITER': BOLD_RED_UNDERLINE,
    'ERROR_LABEL': BOLD_MAGENTA,
    'ERROR_MESSAGE': MAGENTA,
    'FAILURE': BOLD_RED,
    'SOURCE_LOCATION': MAGENTA,
    'TRACE_CALL': BOLD_GREEN,
    'TRACE_EXIT': BOLD_GREEN,
    'TRACE_REDO': BOLD_YELLOW,
    'TRACE_FAIL': BOLD_RED,
    'TRACE_EXCEPTION': BOLD_MAGENTA,
}


def can_colorize(output_fd, enabled=True):
    if os.environ.get('NO_COLOR') is not None:
        return False
    if not enabled:
        return False
    if os.environ.get('FORCE_COLOR') is not None:
        return True
    if os.environ.get('TERM') == 'dumb':
        return False
    return os.isatty(output_fd)


def styled(text, tag, output_fd=1):
    if not text or not can_colorize(output_fd):
        return text
    return THEME[tag] + text + RESET


def filelink(filename, output_fd=1):
    """OSC 8 file link, as in PyPy's traceback formatter.

    Escape URI bytes (including UTF-8) and control characters in the label.
    Keep pseudo filenames such as <stdin> as plain text.
    """
    if (not filename or not can_colorize(output_fd) or
            (filename.startswith('<') and filename.endswith('>'))):
        return filename
    path = os.path.abspath(filename)
    uri = ['file://']
    hexchars = '0123456789ABCDEF'
    for char in path:
        code = ord(char)
        if ('a' <= char <= 'z' or 'A' <= char <= 'Z' or
                '0' <= char <= '9' or char in '/-._~'):
            uri.append(char)
        else:
            uri.append('%' + hexchars[code >> 4] + hexchars[code & 15])
    label = []
    for char in filename:
        code = ord(char)
        if code < 32 or code == 127:
            label.append('\\x' + hexchars[code >> 4] + hexchars[code & 15])
        else:
            label.append(char)
    return '\x1b]8;;' + ''.join(uri) + '\x1b\\' + ''.join(label) + '\x1b]8;;\x1b\\'
