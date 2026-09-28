"""Compare two translated executables on rule body workloads (Python 3).

Usage: python3 tools/benchmark_operations.py BASELINE EXPERIMENT [--count N]
Each sample uses a fresh process, including startup and JIT warmup. Runs are
interleaved; medians are reported. These synthetic workloads are deliberately
small and do not establish application-wide speedups.
"""
import argparse
import os
import statistics
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline')
    parser.add_argument('experiment')
    parser.add_argument('--count', type=int, default=200000)
    parser.add_argument('--rounds', type=int, default=3)
    args = parser.parse_args()
    executables = [os.path.abspath(args.baseline), os.path.abspath(args.experiment)]
    workloads = [
        ('countdown', 'step.'),
        ('full_conjunction', 'step :- ' + ', '.join(['X = f(a)', 'X == f(a)'] * 16) + '.'),
        ('early_failure', 'step :- (rejected ; true).\nrejected :- fail, ' +
         ', '.join(['sink(f(X), g(X))'] * 32) + '.'),
        ('backtracking', 'choice(a). choice(b).\nstep :- (candidate, fail ; true).\n'
         'candidate :- choice(Y), X = Y, X == Y.'),
    ]
    with tempfile.TemporaryDirectory(prefix='pyrolog-operations-bench-') as directory:
        for name, source in workloads:
            path = os.path.join(directory, name + '.pl')
            with open(path, 'w') as stream:
                stream.write(source + '\nloop(0) :- !.\n'
                             'loop(N) :- step, M is N - 1, loop(M).\n'
                             ':- loop(%d), write(done), nl.\n' % args.count)
            for mode in ['off', 'threshold=200']:
                samples = [[], []]
                for repeat in range(args.rounds):
                    for index in ([0, 1] if repeat % 2 == 0 else [1, 0]):
                        start = time.monotonic()
                        result = subprocess.run([executables[index], '--jit', mode, path],
                                                input=b'halt.\n', stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE, check=True)
                        elapsed = time.monotonic() - start
                        assert result.stdout.startswith(b'done\n'), (result.stdout, result.stderr)
                        assert b'ERROR' not in result.stdout, result.stdout
                        assert not result.stderr, result.stderr
                        samples[index].append(elapsed)
                old, new = [statistics.median(values) for values in samples]
                print('%-18s %-14s baseline %.4fs operations %.4fs ratio %.3f samples %r' %
                      (name, mode, old, new, new / old, samples), flush=True)


if __name__ == '__main__':
    main()
