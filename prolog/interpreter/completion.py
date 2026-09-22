"""Predicate-name completion without executing Prolog code."""
from rpyrepl.completion import Completer, Completion
from prolog.interpreter.highlighting import PrologHighlighter


def identifier_char(char):
    return ('a' <= char <= 'z' or 'A' <= char <= 'Z' or
            '0' <= char <= '9' or char == '_')


def plain_name(name):
    if not name or not 'a' <= name[0] <= 'z':
        return False
    for char in name:
        if not identifier_char(char):
            return False
    return True


class PrologCompleter(Completer):
    def __init__(self, engine):
        self.engine = engine
        self.highlighter = PrologHighlighter()

    def complete(self, text, pos):
        from prolog.builtin.register import builtin_names
        assert pos >= 0
        start = pos
        while start > 0 and identifier_char(text[start - 1]):
            start -= 1
        assert start >= 0
        stem = text[start:pos]
        qualified = start > 0 and text[start - 1] == ':'
        # Start with unquoted predicate identifiers; neither variables nor
        # quoted text, comments, filenames or operators expand. An empty
        # qualified stem lists the predicates available in that module.
        if not plain_name(stem) and not (qualified and not stem):
            return Completion(pos, [])
        probe = start - 1 if not stem else start
        for color in self.highlighter.gen_colors(text):
            if (color.tag in ('STRING', 'COMMENT') and
                    color.span.start <= probe < color.span.end):
                return Completion(pos, [])
        module = self.engine.modulewrapper.current_module
        if qualified:
            end = start - 1
            begin = end
            while begin > 0 and identifier_char(text[begin - 1]):
                begin -= 1
            assert 0 <= begin <= end
            name = text[begin:end]
            if not plain_name(name):
                return Completion(pos, [])
            module = self.engine.modulewrapper.modules.get(name, None)
            if module is None:
                return Completion(pos, [])
        names = {}
        self.add_module(names, module, stem)
        if not qualified:
            system = self.engine.modulewrapper.system
            if system is not None:
                self.add_module(names, system, stem)
            for name in builtin_names:
                if plain_name(name) and name.startswith(stem):
                    names[name] = True
            for name in self.engine.modulewrapper.modules:
                if plain_name(name) and name.startswith(stem):
                    names[name + ':'] = True
        return Completion(start, names.keys())

    def add_module(self, names, module, stem):
        for signature, function in module.functions.iteritems():
            name = signature.name
            if (function.rulechain is not None and plain_name(name) and
                    name.startswith(stem)):
                names[name] = True
