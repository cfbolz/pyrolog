from rpython.rlib.listsort import TimSort
from prolog.interpreter import term


def format_answer(bindings, goals, engine):
    """Render projected bindings and goals with shared names and cycle labels."""
    from prolog.builtin import formatting
    output = []
    f = formatting.TermFormatter(engine, quoted=True, max_depth=20)
    factorizer = formatting.CycleFactorizer()
    names = [name for name in bindings if not name.startswith("_")]
    TimSort(names).sort()
    # Choose names before traversing any answer, including roots reached through
    # another answer. Aliases consistently use the first visible name.
    for name in names:
        value = bindings[name].dereference(None)
        if isinstance(value, term.Var):
            if value not in f.variable_names:
                f.variable_names[value] = name
        elif isinstance(value, term.Callable) and value.argument_count() > 0:
            if value not in factorizer.preferred:
                label = term.BindingVar()
                factorizer.preferred[value] = label
                f.variable_names[label] = name
    values = [factorizer.visit(bindings[name]) for name in names]
    residuals = [factorizer.visit(goal) for goal in goals]
    definitions = {}
    for binding in factorizer.bindings:
        definitions[binding.argument_at(0)] = binding.argument_at(1)
    printed = {}
    for i in range(len(names)):
        name = names[i]
        value = values[i]
        if value in definitions and f.variable_names.get(value) == name:
            printed[value] = None
            value = definitions[value]
        elif (isinstance(value, term.Var)
              and f.variable_names.get(value) == name):
            continue  # An unconstrained variable needs no X = X equation.
        val = f.format(value)
        output.append("%s = %s\n" % (name, val))
    for binding in factorizer.bindings:
        label = binding.argument_at(0)
        if label not in printed:
            output.append("%s = %s\n" % (f.format(label), f.format(binding.argument_at(1))))
    for goal in residuals:
        output.append("%s\n" % f.format(goal))
    return "".join(output)
