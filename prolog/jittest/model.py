"""Reuse PyPy's JIT log model, with Prolog predicate selection."""
from pypy.module.pypyjit.test_pypy_c.model import Log as PyPyLog


class Log(PyPyLog):
    def filter_loops(self, predicate=None, **kwds):
        """Select by exact name/arity; return the hot loop by default.

        Pass is_entry_bridge=True for the preamble, or '*' for the full trace.
        A trace can start with bookkeeping before its first debug location.
        """
        result = []
        for loop in self.loops:
            location = next((chunk.bytecode_name
                             for chunk in loop.flatten_chunks()
                             if chunk.bytecode_name), None)
            if predicate is None or (location and
                                     location.split()[0] == predicate):
                result.append(self._filter(loop, **kwds))
        return result
