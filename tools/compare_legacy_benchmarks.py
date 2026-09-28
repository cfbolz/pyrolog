"""Run benchmarks-pyrolog's Python 2 driver with PyPy, preserving its queries.

Usage: pypy tools/compare_legacy_benchmarks.py SUITE BEFORE AFTER OUTPUT
The copied driver gets psutil compatibility fixes and a five-minute watchdog.
By default each process retains the legacy five timed samples, including initialization
before each sample. Raw output and per-sample times are saved for inspection.
"""
import argparse
import imp
import json
import os
import shutil
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite')
    parser.add_argument('before')
    parser.add_argument('after')
    parser.add_argument('output')
    parser.add_argument('--rounds', type=int, default=3)
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--jit', choices=['default', 'off'], default='default')
    parser.add_argument('--benchmarks', nargs='*')
    parser.add_argument('--fix-reducer-escapes', action='store_true')
    parser.add_argument('--iterations', type=int, help='override initialize(integer) in selected workloads')
    args = parser.parse_args()
    suite = os.path.abspath(args.suite)
    output = os.path.abspath(args.output)
    binaries = [os.path.abspath(args.before), os.path.abspath(args.after)]
    if not os.path.isdir(output):
        os.makedirs(output)
    if os.path.exists(os.path.join(output, 'samples.jsonl')):
        parser.error('output already contains results; use a fresh directory')
    work = os.path.join(output, 'suite')
    if not os.path.isdir(work):
        os.makedirs(work)
        for name in os.listdir(suite):
            if name.endswith('.pl') or name == 'driver.py':
                shutil.copyfile(os.path.join(suite, name), os.path.join(work, name))
        shutil.copytree(os.path.join(suite, 'support'), os.path.join(work, 'support'))
        path = os.path.join(work, 'driver.py')
        source = open(path).read()
        source = source.replace('range(5)', 'range(%s)' % args.samples)
        source = source.replace('len(res) != 5', 'len(res) != %s' % args.samples)
        source = source.replace('self._process.get_memory_info()[0]',
                                'self._process.memory_info()[0]')
        source = source.replace('max(usage) /', 'max(usage or [0]) /')
        source = source.replace('        try:\n            while True:',
                                '        deadline = time.time() + 300\n'
                                '        try:\n            while True:')
        source = source.replace('if usage > maxusage:',
                                'if usage > maxusage or time.time() > deadline:')
        source = source.replace('trying to use too much memory:',
                                'watchdog: memory or time limit:')
        with open(path, 'w') as stream:
            stream.write(source)
    driver = imp.load_source('legacy_driver', os.path.join(work, 'driver.py'))
    names = args.benchmarks or sorted(name[:-3] for name in os.listdir(work)
                                      if name.endswith('.pl'))
    if args.fix_reducer_escapes:
        path = os.path.join(work, 'reducer.pl')
        source = open(path).read()
        old = "'=" + chr(92) + "='"
        new = "'=" + chr(92) * 2 + "='"
        if source.count(old) != 2:
            raise ValueError('expected two legacy quoted escapes in reducer.pl')
        with open(path, 'w') as stream:
            stream.write(source.replace(old, new))
    if args.iterations is not None:
        import re
        for name in names:
            path = os.path.join(work, name + '.pl')
            source = open(path).read()
            source, count = re.subn(r'initialize\(10000000\)',
                                   'initialize(%s)' % args.iterations, source)
            if count != 1:
                raise ValueError('expected one 10000000 initializer in ' + name)
            with open(path, 'w') as stream:
                stream.write(source)
    os.chdir(work)
    results = open(os.path.join(output, 'samples.jsonl'), 'a')
    for name in names:
        for repeat in range(args.rounds):
            order = [0, 1] if repeat % 2 == 0 else [1, 0]
            round_failed = False
            for index in order:
                label = ['before', 'after'][index]
                logpath = os.path.join(output, '%s-%s-%s.log' % (name, repeat, label))
                row = dict(benchmark=name, round=repeat, version=label,
                           executable=binaries[index], log=logpath,
                           samples=args.samples, iterations=args.iterations, jit=args.jit,
                           reducer_escapes_fixed=args.fix_reducer_escapes)
                start = time.time()
                oldout, olderr = sys.stdout, sys.stderr
                with open(logpath, 'w') as log:
                    try:
                        sys.stdout = sys.stderr = log
                        command = binaries[index]
                        if args.jit == 'off':
                            command += ' --jit off'
                        samples = driver.run_single(driver.py.path.local(name + '.pl'),
                            (command, 'pyrologtime.pl'), verbose=True)
                        row['samples_ms'] = samples
                    except Exception as exc:
                        row['error'] = repr(exc)
                    finally:
                        sys.stdout, sys.stderr = oldout, olderr
                raw = open(logpath).read()
                row['elapsed_s'] = time.time() - start
                valid = (isinstance(row.get('samples_ms'), list) and
                         len(row['samples_ms']) == args.samples and 'ERROR' not in raw and
                         'Traceback' not in raw and 'watchdog:' not in raw)
                row['status'] = 'ok' if valid else 'failed'
                results.write(json.dumps(row, sort_keys=True) + '\n')
                results.flush()
                print '%-18s round %s %-6s %s %s (%.1fs)' % (
                    name, repeat, label, row['status'], row.get('samples_ms', row.get('error')),
                    row['elapsed_s'])
                sys.stdout.flush()
                if not valid:
                    round_failed = True
            if round_failed:
                # Still run the paired executable before stopping repetitions.
                break
    results.close()


if __name__ == '__main__':
    main()
