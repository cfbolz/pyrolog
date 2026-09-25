from rpython.translator.translator import TranslationContext
from prolog.interpreter.lexer import UnicodeLexer
from prolog.interpreter.termparser import Parser, OperatorTable, SyntaxError
from prolog.interpreter import term


def test_parser_is_rpython():
    operators = OperatorTable()
    operators.add('+', 500, 'yfx')
    operators.add('~', 500, 'fy')
    operators.add('!', 500, 'yf')

    def entry(source):
        try:
            result = Parser(UnicodeLexer().tokenize(source, eof=True), operators).parse()
        except SyntaxError as exc:
            offset = exc.primary.start.i
            if exc.secondary is not None:
                offset += exc.secondary.start.i
            return -1 - offset
        if isinstance(result, term.Number):
            return result.num
        return result.argument_count()

    context = TranslationContext()
    context.config.translation.list_comprehension_operations = True
    context.buildannotator().build_types(entry, [str])
    context.buildrtyper().specialize()
