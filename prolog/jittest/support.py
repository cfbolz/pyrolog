"""Process handling for translated Prolog tests."""
import os
import subprocess
import pytest
from rpython.tool import logparser
from prolog.jittest.model import Log


def run_log(tmpdir, source, queries, jit_options="threshold=40", send_halt=True):
    executable = os.environ.get('PYROLOG_EXECUTABLE',
        os.path.join(os.path.dirname(__file__), '..', '..', 'pyrolog-c'))
    if not os.path.isfile(executable):
        if 'PYROLOG_EXECUTABLE' in os.environ:
            pytest.fail('PYROLOG_EXECUTABLE does not exist: ' + executable)
        pytest.skip('build pyrolog-c or set PYROLOG_EXECUTABLE')
    program = tmpdir.join('program.pl')
    program.write(source)
    logfile = tmpdir.join('jit.log')
    env = os.environ.copy()
    env['PYPYLOG'] = 'jit-log-opt,jit-summary:' + str(logfile)
    process = subprocess.Popen(
        [executable, '--jit', jit_options, str(program)], env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if send_halt:
        queries += '\nhalt.\n'
    stdout, stderr = process.communicate(queries)
    assert process.returncode == 0, stderr
    assert not stderr
    assert 'ERROR' not in stdout, stdout
    assert 'ParseError' not in stdout, stdout
    rawlog = logparser.parse_log_file(str(logfile))
    log = Log(logparser.extract_category(rawlog, 'jit-log-opt-'))
    log.result = stdout
    return log


class BaseTestPyrologC(object):
    @pytest.fixture(autouse=True)
    def setup_workdir(self, tmpdir):
        self.tmpdir = tmpdir

    def run(self, src, call, **jitopts):
        jitopts.setdefault('threshold', 200)
        options = ','.join('%s=%s' % item for item in sorted(jitopts.items()))
        return run_log(self.tmpdir, src, call + '\n',
                       options, send_halt=False)

    def run_and_check(self, src, call, **jitopts):
        interpreted = run_log(self.tmpdir, src, call + '\n',
                              'off', send_halt=False)
        compiled = self.run(src, call, **jitopts)
        assert not interpreted.loops, 'JIT disabled run produced a trace'
        assert compiled.loops, 'JIT enabled run did not compile'
        assert interpreted.result == compiled.result
        return compiled
