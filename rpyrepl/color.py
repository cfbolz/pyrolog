"""CPython/pyrepl palette and environment policy, adapted for output fds."""
import os

BOLD = '\x1b[1m'
BOLD_BLUE = '\x1b[1;34m'
BOLD_MAGENTA = '\x1b[1;35m'
BOLD_RED = '\x1b[1;31m'
BOLD_GREEN_UNDERLINE = '\x1b[1;4;32m'
BOLD_RED_UNDERLINE = '\x1b[1;4;31m'
CYAN = '\x1b[36m'
GREEN = '\x1b[32m'
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


def styled(text, tag):
    if not text:
        return text
    return THEME[tag] + text + RESET
