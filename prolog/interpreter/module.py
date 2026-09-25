from rpython.rlib import jit
from prolog.interpreter.signature import Signature
from prolog.interpreter import error, term
from prolog.interpreter.term import Callable, Atom
from prolog.interpreter.function import _make_toplevel_rule
from prolog.interpreter.helper import unwrap_predicate_indicator

class VersionTag(object):
    pass

class ModuleWrapper(object):
    _immutable_fields_ = ["version?"]

    def __init__(self, engine):
        self.engine = engine
        self.user_module = Module("user")
        self.modules = {"user": self.user_module} # all known modules
        self.seen_modules = {}
        self.current_module = self.user_module
        self.libs = []
        self.system = None
        self.version = VersionTag()

    def init_system_module(self):
        from prolog.builtin.sourcehelper import get_source
        source, file_name = get_source("system.pl")
        self.engine.runstring(source, file_name)
        self.system = self.modules["system"]
        self.current_module = self.user_module

    def get_module(self, name, errorterm):
        self = jit.promote(self)
        module = self._get_module(name, self.version)
        if module is not None:
            return module
        assert isinstance(errorterm, Callable)
        error.throw_existence_error("procedure",
            errorterm.get_prolog_signature())

    def get_or_make_module(self, name):
        module = self._get_module(name, self.version)
        if module is not None:
            return module


    @jit.elidable
    def _get_module(self, name, version):
        return self.modules.get(name, None)

    def add_module(self, name, exports = []):
        from prolog.builtin.parseraccess import declare_exported_operator
        mod = Module(name)
        for export in exports:
            export = export.dereference(None)
            if (isinstance(export, Callable) and export.name() == 'op' and
                    export.argument_count() == 3):
                mod.operator_exports.append(
                    declare_exported_operator(mod.operators, export))
            else:
                mod.exports.append(Signature.getsignature(
                        *unwrap_predicate_indicator(export)))
        self.current_module = mod
        self.modules[name] = mod
        self.version = VersionTag()


class Module(object):
    _immutable_fields_ = ["name", "nameatom", "_toplevel_rule", "version?"]
    def __init__(self, name):
        from prolog.interpreter.parsing import make_operator_table, default_operations
        self.name = name
        self.operators = make_operator_table(default_operations)
        self.nameatom = Atom(name)
        self.functions = {}
        self.version = VersionTag()
        self.meta_predicates = {}
        self.exports = []
        self.operator_exports = []
        self._toplevel_rule = _make_toplevel_rule(self)

    def add_meta_predicate(self, signature, arglist):
        self.meta_predicates[signature] = arglist
        func = self.lookup(signature)
        if func is not None:
            func.meta_args = arglist

    def lookup(self, signature):
        self = jit.promote(self)
        return self._lookup(signature, self.version)

    @jit.elidable
    def _lookup(self, signature, version):
        return self.functions.get(signature, None)

    def use_module(self, module, imports=None):
        from prolog.builtin.parseraccess import declare_exported_operator
        if imports is None:
            importlist = module.exports
            for declaration in module.operator_exports:
                declare_exported_operator(self.operators, declaration)
        else:
            importlist = []
            for pred in imports:
                if pred in module.exports:
                    importlist.append(pred)
        for sig in importlist:
            try:
                function = module.functions[sig]
            except KeyError:
                pass
            else:
                if self.functions.get(sig, None) is not function:
                    self.functions[sig] = function
                    self.version = VersionTag()

    def __repr__(self):
        return "Module('%s')" % self.name
        
