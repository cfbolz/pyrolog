# Rule operation experiment

Rules retain their numbered source body for database operations and also hold
an immutable array of operations. Each invocation owns an array of locals;
`NumberedVar.num` indexes that array. An `OperationContinuation` holds the
program counter and the caller's continuation. Continuations are persistent:
resuming a choice point cannot observe a program counter advanced in place.

A call operation instantiates only its goal, immediately before calling it.
Conjunction nodes are removed entirely. Ordinary disjunction emits a choice,
left branch, jump, and right branch. The failure continuation restores the
heap before entering the right branch. Existing cut scopes also discard these
choice points. All other control constructs remain opaque call templates,
including `if-then-else` and disjunctions with variable operands. Malformed
conjunctions remain opaque to preserve eager operand errors.

All numbered body locals are allocated before the first operation executes.
Lazy allocation into the shared local array is unsafe: a local first used
after an earlier choice point would otherwise retain an untrailed binding on
retry. Singleton variables can still be allocated when their one goal runs.

This is an incremental compiler, not a complete replacement for term-based
execution. Reached goal terms and opaque control subtrees are still copied.
A goal reached repeatedly by backtracking is instantiated on each visit, so
this can trade fewer upfront allocations for more work on retries. Compound
argument construction, builtin specialization, and additional control flow
are separate possible next steps.

## Reproducing validation

With the project's PyPy 2.7 and RPython checkout:

```sh
PYTHONPATH=/home/cfbolz/projects/gitpypy pypy -m pytest -q \
  prolog/interpreter/test prolog/builtin/test prolog/prolog_modules/test
CC=gcc-12 PYTHONPATH=/home/cfbolz/projects/gitpypy pypy \
  /home/cfbolz/projects/gitpypy/rpython/bin/rpython --batch --opt=jit \
  --output=pyrolog-operations-or-c targetprologstandalone.py
PYROLOG_EXECUTABLE="$PWD/pyrolog-operations-or-c" \
  PYTHONPATH=/home/cfbolz/projects/gitpypy pypy -m pytest -q prolog/jittest
python3 tools/benchmark_operations.py BASELINE_BINARY OPERATIONS_BINARY
```

The benchmark runs four synthetic workloads in fresh processes, with the JIT
both enabled and disabled. It alternates executable order over three rounds
and reports medians including startup and warmup. The baseline source is the
parent of commit `a5623d0`; build it separately using the same toolchain.

## Results (2026-09-28)

Baseline: `b689794`. Operation implementation: through `dc6015f`.
Both binaries were translated with the same local PyPy/RPython checkout,
`--opt=jit`, and GCC 12. Compilation and test processes had finished before
measurement. Command:

```sh
python3 tools/benchmark_operations.py /tmp/pyrolog-operations-baseline-c \
  /tmp/pyrolog-operations-final-c --count 1000000
```

Median seconds over three interleaved samples, one million iterations each:

| Workload | JIT | Baseline | Operations | Operations / baseline |
| --- | --- | ---: | ---: | ---: |
| Countdown | off | 0.2936 | 0.2575 | 0.877 |
| Complete conjunction | off | 3.5648 | 2.5923 | 0.727 |
| Early failure | off | 1.7611 | 0.4465 | 0.254 |
| Backtracking | off | 1.0113 | 0.9521 | 0.941 |
| Countdown | on | 0.0046 | 0.0051 | 1.114 |
| Complete conjunction | on | 0.2329 | 0.2267 | 0.973 |
| Early failure | on | 0.0070 | 0.0054 | 0.768 |
| Backtracking | on | 0.0218 | 0.0197 | 0.902 |

The interpreter benefits most when failure skips a large body suffix. These
synthetic results do not establish an application-wide speedup. Several JIT
samples last only a few milliseconds including process startup; their ratios
are especially sensitive to startup and warmup, and are not strong evidence
of steady-state changes. Hot loops already eliminate much of the old copying.

Validation:

- Prolog unit suite: **3,184 passed, 11 skipped, 74 expected failures**.
- Translated suite: **238 passed**, with JIT-on/JIT-off comparisons.
- The unit suite includes **500 generated control-flow programs** compared
  with the legacy executor, checking ordered answers with conjunction,
  disjunction, cut, failure, and unification.
- Existing allocation-free JIT checks still pass. One exact trace expectation
  was updated from body-term fields to program-counter/local fields; its
  exact matching remains in place.

`RuleContinuation.activate` needs `jit.unroll_safe`: its local initialization
loops have rule-constant bounds. Without this hint the JIT treats activation
as an opaque call, forces interpreter allocations, and loses the old tight
loops. The annotation is essential to the experiment's JIT behavior.

## Existing benchmark suite

A subsequent before/after run of `benchmarks-pyrolog` under its original
Python 2 driver, run with PyPy, found about 5.1% lower elapsed time across its
15 application workloads with the JIT enabled. The gains vary by workload.
See the [complete legacy-suite results](benchmark-results/rule-operations/README.md)
for all 23 workloads, longer-run checks, compatibility fixes, raw measurements,
and reproduction commands.

## Tail calls through disjunctions

After the recorded benchmark runs, a continuation-space regression was fixed
in `ea103bf`. A call at the end of a disjunction's left branch used to return
to a `JumpOperation`, even when the jump led directly out of the rule. This
retained both an operation continuation and additional cut-scope continuations
on each recursive call. The driver still used a loop, but the heap-resident
success-continuation chain grew with recursion depth.

The compiler now resolves forward jump chains, from the end of the operation
array backward, and stores the final successor on each call and choice. Tail
calls pass the caller's continuation directly. There is no runtime jump-chain
walk. Real work following a disjunction remains a continuation.

For 100 recursive calls after a cut inside a branch, the previous maximum
success-continuation depth was 201; it is now 2, matching legacy execution.
Tests also cover nested branch exits, entry through a right branch, ordinary
conjunctions, and recursive calls with genuine work left afterward.

The full Prolog suite passes: 3,186 passed, 11 skipped, 74 expected failures.
The benchmark tables above intentionally retain their original, pre-fix
binaries and measurements.

The tail-call build also passes all 239 translated/JIT tests. The new translated
regression rejects stores into newly allocated `OperationContinuation` frames
in the recursive hot loop; it fails on the pre-fix binary and passes after jump
threading. Existing exact trace expectations pass without further changes.
