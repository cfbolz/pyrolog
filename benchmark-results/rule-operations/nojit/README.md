# Interpreter-only legacy suite comparison

Both binaries ran with **`--jit off`**. The geometric mean of after/before
time ratios across the 15 application benchmarks is 0.9535: about **4.7% less
elapsed time**, excluding the eight `iterate*` microbenchmarks. Gains vary:
Boyer, mu, naive reverse, and zebra regress in this run.

The Python 2 driver ran under PyPy. Each workload ran in three fresh processes
per binary, in alternating before/after order, with **one timed sample per
process**. The table shows the median of those three samples. Negative changes
favor operations. There is no JIT warmup; this deliberately differs from the
five-sample JIT protocol, so the two tables are not a direct measurement of
JIT speedup. Workload initialization and loading remain outside the timed region.

The binaries are the same as in the JIT comparison: before `b689794`, after
runtime through `dc6015f`. These measurements were completed **before the
subsequent disjunction tail-call fix** and preserve that comparison point.
The discovered continuation-space regression is present in the after binary.

All 23 workloads completed all six processes (138 successful records). The
three starred cases use the same 100,000-iteration override as the JIT table,
instead of 10,000,000. The same quoting fix was applied to reducer. Other
workloads are unchanged. `iterate_assert` initializes only once in this protocol,
so it does not accumulate duplicate assertions between samples in one process.

| Benchmark | Before (ms) | After (ms) | Time change |
| --- | ---: | ---: | ---: |
| arithmetic | 1103 | 941 | -14.7% |
| boyer | 203 | 224 | +10.3% |
| chat_parser | 15385 | 14073 | -8.5% |
| crypt | 327 | 279 | -14.7% |
| deriv | 1416 | 1260 | -11.0% |
| iterate | 1997 | 1911 | -4.3% |
| iterate_assert * | 22 | 21 | -4.5% |
| iterate_call | 4440 | 3978 | -10.4% |
| iterate_cut * | 40 | 36 | -10.0% |
| iterate_exception * | 90 | 81 | -10.0% |
| iterate_failure | 5244 | 5166 | -1.5% |
| iterate_findall | 5560 | 5499 | -1.1% |
| iterate_if | 3874 | 4017 | +3.7% |
| meta_nrev | 705 | 676 | -4.1% |
| mu | 539 | 591 | +9.6% |
| nrev | 325 | 345 | +6.2% |
| poly | 12 | 12 | +0.0% |
| primes | 453 | 428 | -5.5% |
| qsort | 767 | 675 | -12.0% |
| queens | 1645 | 1591 | -3.3% |
| reducer | 4270 | 3834 | -10.2% |
| tak | 213 | 185 | -13.1% |
| zebra | 2350 | 2514 | +7.0% |

## Reproduction and data

[Raw samples](samples.jsonl), [CSV summary](summary.csv), and
[binary hashes and environment](metadata.json) are retained here. The original
benchmark directory was not modified. Small differences should be interpreted
with the normal caution for three samples and millisecond-resolution timing.

```sh
pypy tools/compare_legacy_benchmarks.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-baseline-c /tmp/pyrolog-operations-final-c \
  /tmp/legacy-nojit --jit off --rounds 3 --samples 1 --fix-reducer-escapes \
  --benchmarks arithmetic boyer chat_parser crypt deriv iterate iterate_call \
  iterate_failure iterate_findall iterate_if meta_nrev mu nrev poly primes \
  qsort queens reducer tak zebra

pypy tools/compare_legacy_benchmarks.py \
  /home/cfbolz/projects/benchmarks-pyrolog \
  /tmp/pyrolog-operations-baseline-c /tmp/pyrolog-operations-final-c \
  /tmp/legacy-nojit-scaled --jit off --rounds 3 --samples 1 --iterations 100000 \
  --benchmarks iterate_assert iterate_cut iterate_exception
```
