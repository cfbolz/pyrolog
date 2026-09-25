# coding: utf-8
"""Source diagnostics rendered as UTF-8 text, independently of terminal I/O."""

from rpython.rlib import rutf8
from rpyrepl.layout import char_width


class _SourceLine(object):
    def __init__(self, raw, start):
        self.start = start
        self.size = len(raw)
        self.columns = [0] * (len(raw) + 1)
        self.character_columns = [0] * (len(raw) + 1)
        parts = []
        pos = 0
        column = 0
        character_column = 0
        while pos < len(raw):
            first = ord(raw[pos])
            size = 1
            if 0xc2 <= first <= 0xdf:
                size = 2
            elif 0xe0 <= first <= 0xef:
                size = 3
            elif 0xf0 <= first <= 0xf4:
                size = 4
            chunk = raw[pos:pos + size]
            try:
                rutf8.check_utf8(chunk, allow_surrogates=False)
                code = rutf8.codepoint_at_pos(chunk, 0)
            except rutf8.CheckError:
                size = 1
                code = -1
            if code == 9:
                width = 8 - column % 8
                chunk = ' ' * width
            elif code < 32 or 0x7f <= code < 0xa0:
                # Includes invalid UTF-8 bytes: diagnostics must still render
                # the input which caused a lexical error. Escape terminal
                # controls instead of allowing them to alter the display.
                escaped = first if code < 0 else code
                digits = '0123456789abcdef'
                chunk = '\\x' + digits[escaped >> 4] + digits[escaped & 15]
                width = len(chunk)
            else:
                width = char_width(code)
            parts.append(chunk)
            for i in range(pos, pos + size):
                self.columns[i] = column
                self.character_columns[i] = character_column
            pos += size
            column += width
            character_column += 1
        self.columns[len(raw)] = column
        self.character_columns[len(raw)] = character_column
        self.text = ''.join(parts)


class _Annotation(object):
    def __init__(self, start, end, label, primary):
        self.start = start
        self.end = max(start + 1, end)
        self.label = label
        self.primary = primary
        self.attach = (self.start + self.end - 1) // 2


def _paint(text, primary, color):
    if not color:
        return text
    return ('\x1b[31m' if primary else '\x1b[36m') + text + '\x1b[0m'


def _annotation_rows(annotations, margin, color):
    # At most two annotations. For overlapping spans, give each its own
    # underline and label, avoiding ambiguous shared connector columns.
    if len(annotations) == 2:
        left, right = annotations
        if left.start > right.start:
            left, right = right, left
        if left.end > right.start:
            return (_annotation_rows([left], margin, color) +
                    _annotation_rows([right], margin, color))
        annotations = [left, right]
    rows = []
    underline = False
    for a in annotations:
        if a.end - a.start > 1 or not a.label:
            underline = True
    if underline:
        row = ''
        column = 0
        for a in annotations:
            row += ' ' * (a.start - column)
            marks = '─' * (a.end - a.start)
            if a.label:
                marks = '─' * (a.attach - a.start) + '┬' + '─' * (a.end - a.attach - 1)
            row += _paint(marks, a.primary, color)
            column = a.end
        rows.append(margin + row)
    pending = [a for a in annotations if a.label]
    if pending:
        right_edge = pending[-1].end + 1
        while pending:
            current = pending.pop()
            row = ''
            column = 0
            for a in pending:
                row += ' ' * (a.attach - column) + _paint('│', a.primary, color)
                column = a.attach + 1
            row += ' ' * (current.attach - column)
            row += _paint('╰' + '─' * (right_edge - current.attach) + ' ' + current.label,
                          current.primary, color)
            rows.append(margin + row)
    return rows


def format_syntax_error(source, filename, error, color=False):
    """Return a complete diagnostic, with the exception message last."""
    lines = []
    offset = 0
    for raw in source.split('\n'):
        # Treat CRLF as one line ending while preserving byte offsets.
        visible = raw[:-1] if raw.endswith('\r') else raw
        lines.append(_SourceLine(visible, offset))
        offset += len(raw) + 1
    primary_line = 0
    for i in range(len(lines)):
        if lines[i].start <= error.primary.start.i:
            primary_line = i
    first = lines[primary_line]
    primary_column = first.character_columns[min(first.size, max(0, error.primary.start.i - first.start))]
    width = len(str(len(lines)))
    margin = ' ' * (width + 2) + '│ '
    rows = [' ' * (width + 2) + '╭─[%s:%d:%d]' %
            (filename, primary_line + 1, primary_column + 1), margin.rstrip()]
    last_shown = -1
    for i in range(len(lines)):
        line = lines[i]
        annotations = []
        next_start = lines[i + 1].start if i + 1 < len(lines) else len(source) + 1
        for secondary in [False, True]:
            location = error.secondary if secondary else error.primary
            if location is None:
                continue
            start = location.start.i
            end = location.end.i
            if start >= next_start or (end <= line.start and start != line.start):
                continue
            label = error.secondary_label if secondary else error.primary_label
            if end > next_start:
                label = ''
            start_byte = min(line.size, max(0, start - line.start))
            end_byte = min(line.size, max(0, end - line.start))
            annotations.append(_Annotation(line.columns[start_byte], line.columns[end_byte],
                                           label, not secondary))
        if not annotations:
            continue
        if last_shown >= 0:
            if i - last_shown == 2:
                rows.append(' ' + (' ' * (width - len(str(i))) + str(i)) + ' │ ' + lines[i - 1].text)
            elif i - last_shown > 2:
                rows.append(' ' * (width + 2) + '⋮')
        rows.append(' ' + (' ' * (width - len(str(i + 1))) + str(i + 1)) + ' │ ' + line.text)
        rows.extend(_annotation_rows(annotations, margin, color))
        last_shown = i
    rows.append('─' * (width + 2) + '╯')
    rows.append(_paint('SyntaxError: ' + error.msg, True, color))
    return '\n'.join(rows) + '\n'
