"""Semantic highlighting spans, following pyrepl.utils (see LICENSE).

Unlike pyrepl's inclusive Unicode-character ranges, offsets here are half-open
UTF-8 byte ranges. Spans are sorted and non-overlapping; gaps are unstyled.
Tags name theme entries, not terminal escape sequences.
"""


class Span(object):
    def __init__(self, start, end):
        self.start = start
        self.end = end


class ColorSpan(object):
    def __init__(self, span, tag):
        self.span = span
        self.tag = tag


class Highlighter(object):
    def get_colors(self, text, pos):
        return self.gen_colors(text)

    def gen_colors(self, text):
        # pyrepl materializes its generator as a list before rendering too.
        return []


def delimiter_colors(text, pos, colors):
    """Overlay the adjacent delimiter pair, ignoring quoted/comment spans.

    Prefer a closing delimiter just typed over the delimiter under the cursor.
    Only adjacent unmatched closers are marked; unfinished openers are normal.
    """
    delimiters = []
    selected = -1
    priority = 0
    color_index = 0
    i = 0
    while i < len(text):
        while color_index < len(colors) and colors[color_index].span.end <= i:
            color_index += 1
        if color_index < len(colors):
            color = colors[color_index]
            if color.span.start <= i and color.tag in ('STRING', 'COMMENT'):
                i = color.span.end
                continue
        char = text[i]
        if char in '()[]{}':
            delimiters.append(i)
            rank = 0
            if i == pos - 1:
                rank = 3 if char in ')]}' else 1
            elif i == pos:
                rank = 2
            if rank > priority:
                selected = i
                priority = rank
        i += 1
    if selected < 0:
        return colors

    stack = []
    partner = -1
    bad_closer = False
    for i in delimiters:
        char = text[i]
        if char in '([{':
            stack.append(i)
        else:
            opening = -1
            if stack:
                opening = stack.pop()
            if opening >= 0 and ((text[opening] == '(' and char == ')') or
                                 (text[opening] == '[' and char == ']') or
                                 (text[opening] == '{' and char == '}')):
                if i == selected:
                    partner = opening
                elif opening == selected:
                    partner = i
            else:
                # Do not claim a match across incorrectly nested delimiters.
                stack = []
                if i == selected:
                    bad_closer = True

    overlay = []
    if partner >= 0:
        first, last = min(selected, partner), max(selected, partner)
        overlay.append(ColorSpan(Span(first, first + 1), 'MATCHING_DELIMITER'))
        overlay.append(ColorSpan(Span(last, last + 1), 'MATCHING_DELIMITER'))
    elif bad_closer:
        overlay.append(ColorSpan(Span(selected, selected + 1), 'MISMATCHED_DELIMITER'))
    else:
        return colors

    # Syntax colours currently leave punctuation unstyled. Merge in source
    # order without changing the original spans or requiring a sorting callback.
    result = []
    index = 0
    for color in colors:
        while index < len(overlay) and overlay[index].span.start < color.span.start:
            result.append(overlay[index])
            index += 1
        result.append(color)
    while index < len(overlay):
        result.append(overlay[index])
        index += 1
    return result
