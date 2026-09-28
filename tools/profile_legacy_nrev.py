"""Collect perf profiles, optimized traces, and GC counters using Python 2/PyPy.

The queries preserve benchmarks-pyrolog's repeated initialization and retained
outputs. Longer runs therefore need not have the same GC behavior as five samples.
"""
import argparse
import json
import os
import re
import subprocess


def gc_summary(raw):
    result = {}
    for category, key in [('gc-minor', 'minor'),
                          ('gc-collect-step', 'major_step'),
                          ('gc-collect-done', 'major')]:
        chunks = re.findall(r'\{' + category + r'\n(.*?)\n\[[^\n]+ ' +
                            category + r'\}', raw, re.S)
        result[key + '_count'] = len(chunks)
        result[key + '_s'] = sum(float(value) for chunk in chunks
            for value in re.findall(r'time taken: +([0-9.]+)', chunk))
    result['promoted_bytes'] = sum(int(value) for value in
        re.findall(r'total size of surviving objects: (\d+)', raw))
    used = re.findall(r'minor collect, total memory used: (\d+)', raw)
    result['max_used_bytes'] = max([int(value) for value in used] or [0])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite')
    parser.add_argument('before')
    parser.add_argument('after')
    parser.add_argument('output')
    parser.add_argument('--mode', choices=['perf', 'gc', 'stat', 'all'], default='all')
    parser.add_argument('--samples', type=int, default=20)
    parser.add_argument('--rounds', type=int, default=6, help='paired stat rounds')
    parser.add_argument('--cpu', type=int, default=2, help='CPU for stat runs only')
    parser.add_argument('--benchmarks', nargs='+', choices=['nrev', 'meta_nrev'],
                        default=['nrev', 'meta_nrev'])
    args = parser.parse_args()
    if args.samples < 1 or args.rounds < 1:
        parser.error('samples and rounds must be positive')
    output = os.path.abspath(args.output)
    if os.path.exists(output):
        parser.error('use a fresh output directory')
    os.makedirs(output)
    suite = os.path.abspath(args.suite)
    binaries = [os.path.abspath(args.before), os.path.abspath(args.after)]
    modes = ['perf', 'gc', 'stat'] if args.mode == 'all' else [args.mode]
    with open(os.path.join(output, 'samples.jsonl'), 'w') as results:
        for mode in modes:
            for name in args.benchmarks:
                query = "consult('%s/support/pyrologtime.pl').\nconsult('%s/%s.pl').\n" % (
                    suite, suite, name)
                query += ', '.join(
                    'initialize(D%d), bench_time(X%d), benchmark(D%d, Out%d), '
                    'bench_time(Y%d), bench_result(X%d, Y%d)' % ((i,) * 7)
                    for i in range(args.samples)) + '.\nhalt.\n'
                input_path = os.path.join(output, name + '.input')
                with open(input_path, 'w') as stream:
                    stream.write(query)
                for repeat in range(args.rounds if mode == 'stat' else 1):
                    for index in ([0, 1] if repeat % 2 == 0 else [1, 0]):
                        version = ['before', 'after'][index]
                        prefix = os.path.join(output, '%s-%s-%s-%d' % (
                            name, version, mode, repeat))
                        env = os.environ.copy()
                        categories = {
                            'perf': 'jit-log-opt,jit-backend-addr,jit-summary',
                            'gc': ('jit-log-opt,jit-backend-counts,jit-summary,'
                                   'gc-minor,gc-collect,gc-set-nursery-size'),
                            'stat': 'gc-minor,gc-collect',
                        }[mode]
                        env['PYPYLOG'] = categories + ':' + prefix + '.jit.log'
                        cmd = [binaries[index]]
                        if mode == 'perf':
                            cmd = ['perf', 'record', '-e', 'cycles:u', '-F', '999',
                                   '-o', prefix + '.perf.data', '--'] + cmd
                        elif mode == 'stat':
                            cmd = ['perf', 'stat', '-x,', '-e',
                                   'task-clock,cycles:u,instructions:u,cache-misses:u,'
                                   'branches:u,branch-misses:u', '-o', prefix + '.stat',
                                   '--', 'taskset', '-c', str(args.cpu)] + cmd
                        with open(input_path) as inp, open(prefix + '.stdout', 'w') as out:
                            with open(prefix + '.stderr', 'w') as err:
                                rc = subprocess.call(cmd, stdin=inp, stdout=out,
                                                     stderr=err, env=env)
                        with open(prefix + '.stdout') as stream:
                            stdout = stream.read()
                        times = [int(value) for value in
                                 re.findall(r'bench_result\((\d+)\)', stdout)]
                        if rc or len(times) != args.samples or 'ERROR' in stdout:
                            raise RuntimeError('failed run; inspect ' + prefix)
                        row = dict(benchmark=name, version=version, mode=mode,
                                   round=repeat, command=cmd, pypylog=env['PYPYLOG'],
                                   samples_ms=times)
                        if mode != 'perf':
                            with open(prefix + '.jit.log') as stream:
                                row.update(gc_summary(stream.read()))
                        else:
                            report = subprocess.check_output([
                                'perf', 'report', '-i', prefix + '.perf.data', '--stdio',
                                '--no-children', '--sort', 'dso,symbol',
                                '--percent-limit', '0.1'])
                            with open(prefix + '.report.txt', 'w') as stream:
                                stream.write(report)
                        results.write(json.dumps(row, sort_keys=True) + '\n')
                        results.flush()
                        print name, version, mode, repeat, times


if __name__ == '__main__':
    main()
