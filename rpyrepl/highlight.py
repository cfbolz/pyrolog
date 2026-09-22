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
    def gen_colors(self, text):
        # pyrepl materializes its generator as a list before rendering too.
        return []
