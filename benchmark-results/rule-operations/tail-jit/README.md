# JIT comparison after the tail-call fix

Fresh measurements compare the original baseline (`b689794`) against operations
with the disjunction tail-call fix (`ea103bf`). **JIT enabled, default parameters.**
The fixed binary previously passed all 239 translated/JIT tests.

The geometric mean of after/before ratios across the 15 application benchmarks
is 0.9740: **2.6% less elapsed time**, excluding the eight `iterate*` workloads.
Qsort remains a notable improvement. Results are mixed, and several small or
variable differences should not be treated as established regressions or gains.

## Method

The original Python 2 driver ran under PyPy. Each workload ran in three fresh
processes per binary; each process measured five samples, including JIT warmup.
Execution order alternated before/after, after/before, before/after. Each table
entry is the median of the three per-process means, in milliseconds. Negative
percentages favor operations. Loading and initialization are outside timing.
All 23 workloads completed: 138 successful process records, 690 timed samples.

The protocol, sizes, and compatibility changes match the previous JIT run.
The three starred iteration workloads use 100,000 iterations on both binaries.
Reducer uses the identical quoted-backslash correction on both. The original
benchmark directory is unchanged. `iterate_assert` preserves the original
repeated-initialization behavior, including accumulating duplicate clauses.

Both baseline and fixed-operation timings were measured afresh. Do not attribute
changes relative to the earlier table solely to the tail-call fix: machine and
per-process timings varied. This compares baseline versus fixed operations;
it does not isolate the tail-call fix against the pre-fix operation binary.

| Benchmark | Before (ms) | After (ms) | Time change |
| --- | ---: | ---: | ---: |
| arithmetic | 35.8 | 33.8 | -5.6% |
| boyer | 58.2 | 57.6 | -1.0% |
| chat_parser | 3353.2 | 3470.4 | +3.5% |
| crypt | 22.8 | 22.6 | -0.9% |
| deriv | 228.8 | 208.8 | -8.7% |
| iterate | 3.6 | 3.8 | +5.6% |
| iterate_assert * | 20.6 | 21.2 | +2.9% |
| iterate_call | 3.6 | 3.6 | +0.0% |
| iterate_cut * | 11.6 | 11.4 | -1.7% |
| iterate_exception * | 59.2 | 56.8 | -4.1% |
| iterate_failure | 17.0 | 14.4 | -15.3% |
| iterate_findall | 72.2 | 73.0 | +1.1% |
| iterate_if | 5.4 | 5.2 | -3.7% |
| meta_nrev | 164.0 | 187.6 | +14.4% |
| mu | 38.4 | 39.6 | +3.1% |
| nrev | 105.2 | 109.4 | +4.0% |
| poly | 53.2 | 49.6 | -6.8% |
| primes | 147.6 | 151.8 | +2.8% |
| qsort | 69.0 | 56.2 | -18.6% |
| queens | 72.0 | 74.4 | +3.3% |
| reducer | 1029.8 | 948.8 | -7.9% |
| tak | 113.6 | 100.8 | -11.3% |
| zebra | 1367.2 | 1300.2 | -4.9% |

## Variability

For example, `meta_nrev` has a +14.4% headline change, but its paired process
means (before / after, milliseconds) were 156.4 / 193.0, 198.6 / 187.6, and
164.0 / 155.2. Two pairs favored operations, while the first favored baseline.
The median-of-means result should therefore not be interpreted as a stable
14% slowdown without further measurements. Millisecond-scale `iterate*`
results also have limited resolution.

[Raw samples](samples.jsonl), [summary CSV](summary.csv), and
[environment and binary hashes](metadata.json) are retained. The CSV additionally
summarizes samples 2-5 separately; that does not guarantee complete JIT warmup.

## Reproduction

```sh
pypy tools/compare_legacy_benchmarks.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-baseline-c /tmp/pyrolog-operations-tail-c \
  /tmp/legacy-tail-jit --rounds 3 --samples 5 --fix-reducer-escapes \
  --benchmarks arithmetic boyer chat_parser crypt deriv iterate iterate_call \
  iterate_failure iterate_findall iterate_if meta_nrev mu nrev poly primes \
  qsort queens reducer tak zebra

pypy tools/compare_legacy_benchmarks.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-baseline-c /tmp/pyrolog-operations-tail-c \
  /tmp/legacy-tail-jit-scaled --rounds 3 --samples 5 --iterations 100000 \
  --benchmarks iterate_assert iterate_cut iterate_exception
```
