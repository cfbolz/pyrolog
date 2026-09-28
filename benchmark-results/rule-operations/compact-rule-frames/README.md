# Compact rule-entry continuations

The first data-layout reduction following the nrev/meta_nrev investigation removes
unused body-only variable slots from `RuleContinuation`.

`Rule.unify_and_standardize_apart_head` formerly returned an environment as large
as the complete body environment, filling only the prefix shared by head and
body. `RuleContinuation.make` inlined that entire environment, including unused
null fields. Its activation already allocates the complete body environment and
initializes body-only variables before executing a goal. The entry frame now
stores only the shared prefix; initialization and trailing behavior are unchanged.

The runtime change is `3016590`, preceded by failing tests in `0e43523`.
Comparisons here use the existing tail-call-fixed binary (`ea103bf`) as **before**,
not the original body-copying baseline.

| Rule | Entry-frame slots before | After |
| --- | ---: | ---: |
| interpret/1 in meta_nrev | 3 | 2 |
| nrev/2 | 4 | 3 |
| myappend/3 | 3 | 3 |
| qsort/3 | 7 | 4 |

On this 64-bit build the translated trace confirms an `interpret/1` frame reduction from 48 to 40 bytes,
excluding the GC header. Object count stays the same. In the meta-append bridge,
that reduces total descriptor sizes from 136 to 128 bytes per step.

Regression tests cover mixed head-only/shared/body-only variables, zero shared
variables, many body-only variables, an arbitrary-size shared environment, and
backtracking over late locals. The translated regression includes bridges and
checks that escaping rule frames have no unused null slots and the expected size.

## Validation

- New unit and translated regressions failed before the change.
- Full Prolog suite: 3,187 passed, 11 skipped, 74 expected failures.
- Additional arbitrary-size shared-environment check passed after extending the test.
- Translated/JIT suite: 240 passed, including the new frame-size regression.
  Existing exact trace expectations did not need changes.
- Build: PyPy/Python 2, GCC 12, RPython `--opt=jit`.

Logs remain at `/tmp/pyrolog-compact-{red,focused,tests,jittests,build}.log`.

## JIT benchmark results

Ten fresh process pairs per workload, alternating before/after order, five timed
samples per process, including warmup. Entries are medians of process means in
milliseconds. Both versions were measured afresh, serially, after all build and
test jobs finished. Negative percentages mean less time.

| Benchmark | Before | After | Time change |
| --- | ---: | ---: | ---: |
| nrev | 106.4 | 105.7 | -0.7% |
| meta_nrev | 165.1 | 133.6 | -19.1% |
| qsort | 37.4 | 37.6 | +0.5% |

`meta_nrev` improved in all ten pairs. The other two changes are too small to
establish an effect. Entry-frame slots shrinking does not guarantee a hot-path
saving when those frames were already virtualized: direct `myappend` has the
same allocations as before.

[Raw samples](samples.jsonl), [summary CSV](summary.csv), and
[environment/binary hashes](metadata.json).

Because the `meta_nrev` timing gain was larger than the allocation-size reduction,
a second experiment pinned execution to CPU 2, using six alternating pairs of
20-sample processes with `perf stat` and GC logging:

| Measure (median per version) | Before | After | Change |
| --- | ---: | ---: | ---: |
| Mean timed sample | 163.125 ms | 138.125 ms | -15.3% |
| Mean excluding first five samples | 158.633 ms | 135.567 ms | -14.5% |
| Process CPU cycles | 13.404 billion | 11.155 billion | -16.8% |
| Process instructions retired | 24.884 billion | 24.635 billion | -1.0% |
| Minor collections | 948 | 893 | -5.8% |
| Total minor-GC time | 1.997 s | 1.387 s | -30.6% |
| Total major-GC step time | 0.902 s | 0.904 s | +0.3% |
| Promoted bytes | 1,394,697,360 | 1,394,570,328 | -0.01% |

The new binary won all six pinned pairs. Perf counters include the whole process;
Prolog timings exclude initialization. All hardware events ran without
multiplexing. [Pinned raw samples, counters, and GC summaries](pinned-samples.json)
and the original `.stat` files are retained.

The measurements support a performance improvement on this machine. The time
saving is concentrated in minor collection, while promotion and instruction
counts barely change. They do not isolate why the gain exceeds the byte saving:
object placement, locality, and generated C layout could contribute. The exact
15-19% magnitude should not be assumed portable to other machines.

## Allocation and execution evidence

In a separate diagnostic run (20 samples, backend execution counters enabled),
the hot meta-append bridge executes 28,916,798 times in **both** versions. Every
other corresponding entry/loop/bridge counter also matches. It now allocates a
40-byte `RuleContinuationSize2`, replacing the 48-byte `RuleContinuationSize3`
and removing its null-field store. The other three allocations remain 24, 24,
and 40 bytes. This saves about 231 MB of allocation across those hot-bridge
executions alone (about 11 MiB per timed benchmark invocation).

| Diagnostic GC measure | Before | After |
| --- | ---: | ---: |
| nrev minor collections | 463 | 463 |
| meta_nrev minor collections | 948 | 900 |
| meta_nrev promoted bytes | 1,394,622,488 | 1,394,791,296 |

The diagnostic run changes machine code by adding counters, so its timing and
collection counts are kept separate from the pinned experiment above.

Optimized traces and execution counters: [nrev before](nrev-before.jit.txt),
[nrev after](nrev-after.jit.txt), [meta_nrev before](meta_nrev-before.jit.txt),
[meta_nrev after](meta_nrev-after.jit.txt).
[GC summaries](gc-samples.jsonl); full logs remain in `/tmp/pyrolog-compact-gc/`.

## Reproduction

```sh
pypy tools/compare_legacy_benchmarks.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-tail-c /tmp/pyrolog-compact-rule-c \
  /tmp/compact-bench-new --rounds 10 --samples 5 --benchmarks nrev meta_nrev qsort

pypy tools/profile_legacy_nrev.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-tail-c /tmp/pyrolog-compact-rule-c \
  /tmp/compact-gc-new --mode gc --samples 20

pypy tools/profile_legacy_nrev.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-tail-c /tmp/pyrolog-compact-rule-c \
  /tmp/compact-stat-new --mode stat --samples 20 --rounds 6 --benchmarks meta_nrev
```
