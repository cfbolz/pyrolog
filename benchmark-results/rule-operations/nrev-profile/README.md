# nrev and meta_nrev: perf and trace investigation

Original baseline `b689794` versus tail-call-fixed operations `ea103bf`, JIT enabled
with default parameters. No runtime changes were made during this investigation.

The earlier +4.0% (`nrev`) and +14.4% (`meta_nrev`) results do not reproduce as
stable slowdowns. Both workloads are dominated by GC. The quadratic append path
has the same allocations in both binaries, and `meta_nrev`'s normalized optimized
traces differ only in the placement of an invalidation guard. There is a small
real representation change in `nrev`'s linear recursion/return path.

## Repeated timings

All entries are milliseconds, median of per-process means. Before and after
processes ran serially, alternating order between pairs. Negative changes mean
less time. The original Python 2 driver and analysis scripts ran under PyPy.

| Protocol | Benchmark | Before | After | Time change |
| --- | --- | ---: | ---: | ---: |
| Original protocol: 10 pairs, 5 samples/process | nrev | 111.70 | 111.80 | +0.1% |
| Original protocol: 10 pairs, 5 samples/process | meta_nrev | 166.30 | 175.80 | +5.7% |
| CPU 2, perf stat + GC logging: 6 pairs, 20 samples/process | nrev | 105.875 | 106.525 | +0.6% |
| CPU 2, perf stat + GC logging: 6 pairs, 20 samples/process | meta_nrev | 190.475 | 184.375 | -3.2% |

These protocols are separate experiments: 20 samples retain more outputs and
repeat initialization more often than five. Neither the last row's improvement
nor the earlier slowdown establishes a stable `meta_nrev` effect. In the pinned
runs, median major-collection counts were 47 versus 44 for `meta_nrev`, with
corresponding differences in GC time and instructions retired. This is consistent
with GC/memory behavior accounting for much of the variation; it does not isolate
a particular cause such as ASLR, cache layout, or collection scheduling.

[Five-sample raw measurements](five-sample-repeats.jsonl),
[pinned samples](stat-samples.jsonl), and
[pinned CPU-counter/GC summaries](stat-summary.json) are retained. The `.stat`
files contain the original perf counters (100% event running time, no multiplexing).
Pinned runs include process startup and shutdown in perf counters; Prolog sample
times exclude initialization, as in the original suite. Dropping the first five
samples in the pinned runs gives +1.0% for `nrev` and -2.3% for `meta_nrev`.

## perf profiles

`perf record -e cycles:u -F 999` on one fresh 20-sample process per binary and
workload. Optimized traces and backend address ranges were recorded concurrently.
These profiles were not CPU-pinned. They contain approximately 2,000 samples for
`nrev` and 3,500 for `meta_nrev`, with no lost samples reported.

Percent of sampled cycles, weighted by sample period:

| Workload | Version | GC routines | memcpy/memmove | JIT code | Other |
| --- | --- | ---: | ---: | ---: | ---: |
| nrev | before | 82.1% | 6.1% | 9.5% | 2.3% |
| nrev | after | 84.4% | 3.9% | 9.6% | 2.2% |
| meta_nrev | before | 78.4% | 8.5% | 11.9% | 1.2% |
| meta_nrev | after | 76.9% | 9.4% | 12.3% | 1.4% |

GC includes `trace__gc_callback*`, `IncrementalMiniMarkGC*`, and `ArenaCollection*`
symbols. JIT samples were matched to the loop/bridge address ranges, including
failure stubs, from `jit-backend-addr`. Memory copying is shown separately because
these are flat profiles, without call-stack attribution.

The largest individual routine is `pypy_g_trace__gc_callback__trace_drag_out`
(37-41%). Other large consumers are nursery evacuation allocation,
`mass_free_in_pages`, old-generation tracing, and remembered-set scanning.
There is no visible new interpreter/operation-dispatch hotspot.

[Profile aggregation](perf-summary.json) retains weighted symbol counts.
Readable perf reports: [nrev before](nrev-before.perf.txt),
[nrev after](nrev-after.perf.txt), [meta_nrev before](meta_nrev-before.perf.txt),
[meta_nrev after](meta_nrev-after.perf.txt).
Raw perf recordings remain under `/tmp/pyrolog-nrev-profile/*.perf.data`.

## What changed in the traces

### nrev

Both versions compile three loops (`range`, `nrev`, `myappend`) and one bridge.
No trace aborts, extra compiled loops, or ongoing recompilation appeared.

The steady-state `myappend/3` loop is unchanged apart from diagnostic locations
and address/variable naming. It allocates **two objects per list element**:

- One 24-byte list cell (`Abstract2`).
- One 24-byte `BindingVar`.

Sizes here are JIT `SizeDescr` values, excluding the GC header. The hot section's
machine-code offsets are identical (576 through 784). The full trace's apparent
56-to-58 operation increase is two `debug_merge_point` operations, not additional
work in the loop.

The linear descent through `nrev/2` differs:

| Old saved return state | New saved return state |
| --- | --- |
| 32-byte `BodyContinuation` | 40-byte `OperationContinuation`, PC = 1 |
| 40-byte copied `myappend/3` term | Four-element locals array |
| 24-byte singleton `[X]`, created eagerly | Singleton `[X]` created on return |
| 24-byte variable for `Z1` | Same variable for `Z1` |

The new locals array also keeps the input-tail local, which the old copied
`myappend` goal did not need. On return, the new bridge reads locals and checks
the PC instead of unpacking a copied call, then constructs `[X]`. This changes
O(N) work; the O(N^2) append loop is unchanged. The bridge has the same 48 bytes
of list-cell/variable allocations as before, plus the deferred singleton's
24 bytes; that singleton was already allocated during descent in the old version.
It is a moved allocation, not a new per-append-element allocation.

Raw optimized traces: [before](nrev-before.jit.txt), [after](nrev-after.jit.txt).
[Normalized diff](nrev.trace.diff).

### meta_nrev

Both versions compile two loops (`range`, `interpret`) and two bridges, with
54 operations in the `interpret` trace and 53/40 in its bridges. The normalized
diff shows **only `guard_not_invalidated` moving past the heap-hook check**;
allocations, loads, stores, and control transfers match. Rule operations and
locals are eliminated on the hot path.

The hot append bridge allocates the same four objects in both binaries:

| Object | Descriptor size |
| --- | ---: |
| Output list cell | 24 bytes |
| Output tail variable | 24 bytes |
| `app/3` goal | 40 bytes |
| `RuleContinuationSize3` | 48 bytes |

That is 136 bytes excluding GC headers, compared with 48 bytes in the direct
`myappend` loop. The bridge jumps back to the **entry** of the `interpret` trace,
which explains why the rule continuation and `app/3` term are materialized.
This is a pre-existing optimization opportunity, not a regression introduced by
operation execution. It also explains why `meta_nrev` can have substantially
more nursery allocation than `nrev` despite similar promoted bytes.

Raw optimized traces: [before](meta_nrev-before.jit.txt),
[after](meta_nrev-after.jit.txt). [Normalized diff](meta_nrev.trace.diff).
Normalization removes machine-code offsets, diagnostic locations, guard failure
argument lists and addresses, and renames variables/constants. It is a reading
aid, not a proof of machine-code equivalence; retain the raw traces for details.

## Independent execution counters and GC logs

A separate 20-sample run enabled `jit-backend-counts` and GC logging. It was not
used as a performance estimate: counter instrumentation changes generated code.

| Measure | nrev before | nrev after | meta_nrev before | meta_nrev after |
| --- | ---: | ---: | ---: | ---: |
| Hot append loop/bridge executions | 28,881,699 | 28,881,699 | 28,916,798 | 28,916,798 |
| Minor collections | 463 | 463 | 948 | 948 |
| Promoted bytes | 1,394,985,488 | 1,395,338,992 | 1,394,584,608 | 1,394,622,488 |
| Completed major collections | 15 | 15 | 43 | 45 |

All other corresponding entry/loop/bridge execution counts also match exactly.
Both binaries used a 4 MiB nursery after startup. Thus this run finds neither
extra execution nor a meaningful increase in promoted data. Major-collection
counts still vary. See [GC and execution-counter summary](gc-summary.json).

## Reproduction and artifacts

The binaries and their SHA-256 hashes are unchanged from the
[tail-call JIT comparison](../tail-jit/metadata.json).
`/tmp/pyrolog-nrev-profile/` retains original perf data, stdout, full GC logs,
per-sample timings, and the original collection/analysis scripts.

A reusable PyPy/Python 2 collection tool now performs the same three experiments:

```sh
pypy tools/profile_legacy_nrev.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-baseline-c /tmp/pyrolog-operations-tail-c \
  /tmp/pyrolog-nrev-profile-new --samples 20 --rounds 6 --cpu 2
```

Use `--mode perf`, `--mode gc`, or `--mode stat` to run just one experiment.
The tool was smoke-tested with five perf samples on both binaries and a
two-sample run of all three collection modes. The
original recordings were made with equivalent temporary scripts; output naming
in the reusable tool differs from the historical filenames.

The original timing protocol was repeated with:

```sh
pypy tools/compare_legacy_benchmarks.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-baseline-c /tmp/pyrolog-operations-tail-c \
  /tmp/pyrolog-nrev-repeats-new --rounds 10 --samples 5 --benchmarks nrev meta_nrev
```

The [analysis scripts](analysis/) accept the original raw-data directory as their
first argument. They retain the original filenames for reprocessing this run.
