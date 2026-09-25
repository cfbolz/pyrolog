"""Predicate-name completion without executing Prolog code."""
from rpyrepl.completion import Completer, Completion
from prolog.interpreter.highlighting import PrologHighlighter
from prolog.interpreter import utf8
from prolog.interpreter.predicates import visible_predicates
from rpython.rlib import rutf8


def plain_name(name):
    return utf8.plain_atom(name)


def identifier_start_backwards(text, end):
    while end > 0:
        previous = rutf8.prev_codepoint_pos(text, end)
        if not utf8.identifier_continue(rutf8.codepoint_at_pos(text, previous)):
            break
        end = previous
    return end


def skip_layout_backwards(text, end, colors):
    while end > 0:
        previous_char = rutf8.prev_codepoint_pos(text, end)
        if utf8.layout(rutf8.codepoint_at_pos(text, previous_char)):
            end = previous_char
            continue
        previous = end
        for color in colors:
            if color.tag == 'COMMENT' and color.span.end == end:
                end = color.span.start
                break
        if previous == end:
            break
    assert end >= 0
    return end


class PrologCompleter(Completer):
    def __init__(self, engine):
        self.engine = engine
        self.highlighter = PrologHighlighter()

    def complete(self, text, pos):
        assert pos >= 0
        start = identifier_start_backwards(text, pos)
        assert start >= 0
        stem = text[start:pos]
        colors = self.highlighter.gen_colors(text)
        separator_end = skip_layout_backwards(text, start, colors)
        qualified = separator_end > 0 and text[separator_end - 1] == ':'
        # Start with unquoted predicate identifiers; neither variables nor
        # quoted text, comments, filenames or operators expand. An empty
        # qualified stem lists the predicates available in that module.
        if not plain_name(stem) and not (qualified and not stem):
            return Completion(pos, [])
        probe = start - 1 if not stem else start
        for color in colors:
            if (color.tag in ('STRING', 'COMMENT') and
                    color.span.start <= probe < color.span.end):
                comment_start = color.span.start
                assert comment_start >= 0
                if (not stem and color.tag == 'COMMENT' and color.span.end == pos
                        and text[comment_start:comment_start + 2] == '/*' and pos >= 2):
                    last = pos - 2
                    assert last >= 0
                    if text[last:pos] == '*/':
                        continue  # Just after a closed block comment.
                return Completion(pos, [])
        module = self.engine.modulewrapper.current_module
        if qualified:
            end = skip_layout_backwards(text, separator_end - 1, colors)
            begin = identifier_start_backwards(text, end)
            assert 0 <= begin <= end
            name = text[begin:end]
            if not plain_name(name):
                return Completion(pos, [])
            module = self.engine.modulewrapper.modules.get(name, None)
            if module is None:
                return Completion(pos, [])
        names = {}
        for signature in visible_predicates(self.engine, module,
                                            include_fallbacks=not qualified):
            name = signature.name
            if plain_name(name) and name.startswith(stem):
                names[name] = True
        if not qualified:
            for name in self.engine.modulewrapper.modules:
                if plain_name(name) and name.startswith(stem):
                    names[name + ':'] = True
        return Completion(start, names.keys())
