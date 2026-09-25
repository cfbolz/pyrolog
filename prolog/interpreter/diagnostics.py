# coding: utf-8
"""Source diagnostics rendered as UTF-8 text, independently of terminal I/O."""


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
    if any(a.end - a.start > 1 or not a.label for a in annotations):
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
    lines = source.split('\n')
    starts = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line) + 1
    primary_line = 0
    for i in range(len(lines)):
        if starts[i] <= error.primary.start.i:
            primary_line = i
    width = len(str(len(lines)))
    margin = ' ' * (width + 2) + '│ '
    rows = [' ' * (width + 2) + '╭─[%s:%d:%d]' %
            (filename, primary_line + 1, error.primary.start.i - starts[primary_line] + 1),
            margin.rstrip()]
    for i in range(len(lines)):
        annotations = []
        for secondary in [False, True]:
            location = error.secondary if secondary else error.primary
            if location is None:
                continue
            start = location.start.i
            end = location.end.i
            line_start = starts[i]
            line_end = line_start + len(lines[i])
            if start > line_end or (end <= line_start and start != line_start):
                continue
            label = error.secondary_label if secondary else error.primary_label
            if end > line_end:
                label = ''
            annotations.append(_Annotation(max(0, start - line_start),
                                           min(len(lines[i]), end - line_start),
                                           label, not secondary))
        if not annotations:
            continue
        rows.append(' ' + str(i + 1).rjust(width) + ' │ ' + lines[i])
        rows.extend(_annotation_rows(annotations, margin, color))
    rows.append('─' * (width + 2) + '╯')
    rows.append(_paint('SyntaxError: ' + error.msg, True, color))
    return '\n'.join(rows) + '\n'
