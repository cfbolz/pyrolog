# Legacy Pyrolog benchmark comparison, 2026-09-28

The operation-based interpreter took about **5.1% less elapsed time** across
this suite's 15 application benchmarks (geometric mean of after/before ratios,
0.9494). This excludes the eight `iterate*` microbenchmarks. The benefit is
uneven: qsort, deriv, and Boyer improved, while several workloads were nearly
unchanged or slightly slower. These are exploratory measurements on one host,
not confidence-bounded estimates of a universal speedup.

## Method

- Before: runtime at `b689794`; after: runtime through `dc6015f`.
- Both existing binaries were built with the same RPython checkout, PyPy,
  GCC 12, and `--opt=jit`. JIT enabled with default parameters on both.
- AMD Ryzen 7 PRO 7840U. Benchmarks ran sequentially, without concurrent builds
  or test runs from this experiment.
- Ran the original Python 2 driver's `run_single` under **PyPy 2.7**, preserving
  its query and five measurements per process. Initialization and source
  loading are outside each timed interval. Timing uses Prolog's
  `statistics(walltime, ...)`, in integer milliseconds.
- Three fresh processes per executable per workload; order alternates
  before/after, after/before, before/after. Each reported number is the median
  of the three per-process means. Negative time changes favor operations.
- The five-sample measurements **include JIT warmup**. `summary.csv` also
  includes a separate calculation excluding the first sample. The later
  20-sample experiment is reported separately below.

No packages needed installation. All changes to the old suite were made in
copies under `/tmp`; `/home/cfbolz/projects/benchmarks-pyrolog` was left intact.

## Compatibility and incomplete original runs

The copied driver uses `psutil.Process.memory_info()` instead of the removed
`get_memory_info()`, tolerates a process exiting before its first RSS sample,
and adds a five-minute watchdog. Its existing 1 GiB RSS limit is retained.
The adapter selects the two binaries and stores raw samples instead of relying
on the old driver's hard-coded executable configuration.

- `reducer` initially failed parsing on the baseline: two quoted `=\=` atoms
  used a single backslash. The copied source doubles those backslashes, with
  the same fix for both binaries. This changes quoting, not the intended atom.
- `iterate_assert`, `iterate_cut`, and `iterate_exception` exceeded the original
  memory limit at 10,000,000 iterations **on both binaries**. Their paired
  results below use **100,000 iterations**, identically on both binaries.
- `iterate_assert` still retains the old behavior of asserting more clauses
  on every initialization; its later samples are not equivalent repetitions
  of the first sample. It is excluded from the application aggregate.

The original failures are retained in `samples.jsonl`; they are not treated
as zero-time successes or silently mixed into the averages.

## Original five-sample comparison

A single asterisk marks the three reduced-size workloads. Two asterisks mark
the reducer quoting fix. All other workloads and sizes are unchanged.

| Benchmark | Before (ms) | After (ms) | Time change |
| --- | ---: | ---: | ---: |
| arithmetic | 31.4 | 29.0 | -7.6% |
| boyer | 63.6 | 56.8 | -10.7% |
| chat_parser | 4070.2 | 3962.2 | -2.7% |
| crypt | 23.8 | 24.8 | +4.2% |
| deriv | 205.4 | 182.6 | -11.1% |
| iterate | 3.2 | 3.2 | +0.0% |
| iterate_assert * | 14.2 | 14.8 | +4.2% |
| iterate_call | 3.2 | 3.4 | +6.2% |
| iterate_cut * | 6.0 | 6.4 | +6.7% |
| iterate_exception * | 35.8 | 37.0 | +3.4% |
| iterate_failure | 16.4 | 14.2 | -13.4% |
| iterate_findall | 73.0 | 73.6 | +0.8% |
| iterate_if | 5.6 | 5.2 | -7.1% |
| meta_nrev | 159.4 | 154.2 | -3.3% |
| mu | 35.6 | 35.6 | +0.0% |
| nrev | 96.2 | 96.6 | +0.4% |
| poly | 40.8 | 38.4 | -5.9% |
| primes | 105.2 | 107.6 | +2.3% |
| qsort | 46.0 | 36.0 | -21.7% |
| queens | 53.2 | 52.0 | -2.3% |
| reducer ** | 539.0 | 513.8 | -4.7% |
| tak | 77.4 | 72.4 | -6.5% |
| zebra | 881.8 | 852.6 | -3.3% |

## Longer-run cross-check

Eight selected workloads ran for 20 samples per process, again in three
alternating pairs of fresh processes. Discarding the first five leaves 15
measured samples per process. The numbers below use the same median-of-means
calculation. This supports gains beyond the first invocation, especially for
qsort, deriv, and Boyer; it does not prove all JIT/GC behavior has stabilized.

The original driver retains earlier inputs and outputs in one conjunction,
so increasing the sample count can change live memory and GC behavior.
Absolute times in this table should therefore not be compared directly with
the five-sample table. Small millisecond-scale changes remain noisy.

| Benchmark | Before (ms) | After (ms) | Time change |
| --- | ---: | ---: | ---: |
| arithmetic | 20.0 | 19.1 | -4.3% |
| boyer | 40.1 | 32.8 | -18.1% |
| crypt | 12.2 | 11.7 | -3.8% |
| deriv | 163.6 | 150.9 | -7.7% |
| meta_nrev | 104.1 | 100.8 | -3.2% |
| primes | 171.7 | 154.1 | -10.2% |
| qsort | 39.1 | 28.7 | -26.6% |
| tak | 67.9 | 64.1 | -5.6% |

## Artifacts and reproduction

- [Raw per-process samples](samples.jsonl), including failed original runs.
- [Five-sample summary](summary.csv), including post-first-sample averages.
- [Longer-run summary](warm-summary.csv).
- [Environment, binary hashes, and original workload hashes](metadata.json).
- Compatibility patches: [driver](driver-compat.patch),
  [reducer](reducer-compat.patch), [iteration sizes](iteration-sizes.patch).
- Adapter: [compare_legacy_benchmarks.py](../../tools/compare_legacy_benchmarks.py).

Use fresh output directories for each command:

```sh
pypy tools/compare_legacy_benchmarks.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-baseline-c /tmp/pyrolog-operations-final-c \
  /tmp/legacy-main --rounds 3

pypy tools/compare_legacy_benchmarks.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-baseline-c /tmp/pyrolog-operations-final-c \
  /tmp/legacy-scaled --rounds 3 --iterations 100000 \
  --benchmarks iterate_assert iterate_cut iterate_exception

pypy tools/compare_legacy_benchmarks.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-baseline-c /tmp/pyrolog-operations-final-c \
  /tmp/legacy-reducer --rounds 3 --fix-reducer-escapes --benchmarks reducer

pypy tools/compare_legacy_benchmarks.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-baseline-c /tmp/pyrolog-operations-final-c \
  /tmp/legacy-warm --rounds 3 --samples 20 \
  --benchmarks arithmetic boyer crypt deriv meta_nrev primes qsort tak
```

The adapter's default five-sample mode is the original protocol. The sample
count override modifies only the repeated query count and expected result
count in the copied driver. The adapter was adjusted after the first full run
to attempt both executables even when the first fails; paired memory-limit
checks were performed separately and recorded.

## Interpreter-only comparison

The same binaries were subsequently measured with `--jit off`, using one
sample per process and three alternating pairs. All 23 workloads completed;
the application geometric mean was 4.7% less elapsed time, with both gains and
regressions. See the [interpreter-only table and raw measurements](nojit/README.md).
These results precede the disjunction tail-call fix.
